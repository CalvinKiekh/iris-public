#!/usr/bin/env python3
"""MCP server exposing the machine inventory to Claude.

The point of the inventory is that Claude stops rediscovering this machine
in every conversation. That only works if Claude can query it directly, so
the same database that backs the HTTP API is also served here.

Read-only by design: it answers questions, it does not change anything.
Register it in ~/.claude/settings.json under mcpServers, or per project in
.mcp.json.

Speaks JSON-RPC 2.0 over stdin/stdout. No third-party dependencies.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import inventory  # noqa: E402

TOOLS = [
    {
        "name": "find_project",
        "description": ("Find a project on this machine by name, path, git "
                        "remote or build command. Returns its path, language, "
                        "git branch and account, and how it is built and run."),
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string",
                                     "description": "name or fragment, e.g. 'maro'"}},
            "required": ["query"],
        },
    },
    {
        "name": "list_projects",
        "description": ("List known projects, newest first. Filter by kind "
                        "(python, node, swift, docker, rust, go, git) or by "
                        "GitHub account."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "account": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "project_environment",
        "description": ("Python environments belonging to a project: path, "
                        "Python version, package count, size on disk. Use this "
                        "before suggesting which interpreter to run."),
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "listening_services",
        "description": ("What is listening on which port right now, and which "
                        "process owns it. Answers 'is my dev server still up' "
                        "and 'what is already using this port'."),
        "inputSchema": {"type": "object", "properties": {
            "refresh": {"type": "boolean",
                        "description": "re-read live instead of using the cache"}}},
    },
    {
        "name": "machine_summary",
        "description": ("Overview: how many projects by kind, how much disk "
                        "the virtualenvs take, which GitHub accounts are in "
                        "use, when the inventory was last refreshed."),
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _text(obj):
    return {"content": [{"type": "text",
                         "text": json.dumps(obj, ensure_ascii=False, indent=1)}]}


def call(name, args):
    if name == "find_project":
        rows = inventory.search(args.get("query", ""), limit=15)
        return _text({"found": len(rows), "projects": rows})
    if name == "list_projects":
        return _text({"projects": inventory.projects(
            kind=args.get("kind"), account=args.get("account"),
            limit=int(args.get("limit") or 40))})
    if name == "project_environment":
        return _text({"envs": inventory.envs(args.get("path"))})
    if name == "listening_services":
        return _text({"services": inventory.services(
            refresh=bool(args.get("refresh")))})
    if name == "machine_summary":
        s = inventory.summary()
        stale, age = inventory.stale()
        s["stale"] = stale
        s["age_hours"] = round(age / 3600, 1)
        return _text(s)
    return {"content": [{"type": "text", "text": f"unknown tool: {name}"}],
            "isError": True}


def respond(rid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": rid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, rid = req.get("method"), req.get("id")

        if method == "initialize":
            respond(rid, {
                "protocolVersion": req.get("params", {})
                                      .get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "iris-inventory", "version": "1.0.0"},
            })
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            respond(rid, {"tools": TOOLS})
        elif method == "tools/call":
            params = req.get("params", {})
            try:
                respond(rid, call(params.get("name", ""),
                                  params.get("arguments") or {}))
            except Exception as exc:        # noqa: BLE001 - report, never die
                respond(rid, {"content": [{"type": "text",
                                           "text": f"Fehler: {exc}"}],
                              "isError": True})
        elif rid is not None:
            respond(rid, error={"code": -32601, "message": f"unknown: {method}"})


if __name__ == "__main__":
    main()
