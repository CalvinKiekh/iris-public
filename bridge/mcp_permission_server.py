#!/usr/bin/env python3
"""Minimal MCP stdio server exposing a single permission-approval tool.

Claude Code is launched with --permission-prompt-tool pointing at this
server's `approve` tool. Every tool call the model wants to make is routed
here first; we forward the decision to the bridge over a unix socket and
block until a client (phone, glasses) answers.

Speaks JSON-RPC 2.0 over stdin/stdout. No third-party dependencies.
"""
import json
import os
import socket
import sys
import uuid

BRIDGE_SOCKET = os.environ.get("IRIS_BRIDGE_SOCKET", "")
SESSION_KEY = os.environ.get("IRIS_SESSION_KEY", "")
DECISION_TIMEOUT = float(os.environ.get("IRIS_PERMISSION_TIMEOUT", "300"))

TOOL_NAME = "approve"


def log(msg):
    # stdout is the JSON-RPC channel, so diagnostics go to stderr only.
    print(f"[iris-permission] {msg}", file=sys.stderr, flush=True)


def ask_bridge(tool_name, tool_input, suggestions):
    """Ask the bridge for a decision. Fail closed: deny when unreachable."""
    request = {
        "kind": "permission_request",
        "id": str(uuid.uuid4()),
        "session_key": SESSION_KEY,
        "tool_name": tool_name,
        "tool_input": tool_input,
        "permission_suggestions": suggestions,
    }
    if not BRIDGE_SOCKET:
        return {"behavior": "deny", "message": "iris: no bridge socket configured"}
    try:
        # Windows has no Unix sockets for Python: there the bridge listens on
        # loopback TCP, given as "tcp:127.0.0.1:<port>".
        tcp = None
        if BRIDGE_SOCKET.startswith("tcp:"):
            host, _, port = BRIDGE_SOCKET[4:].rpartition(":")
            tcp = (host, int(port))
        family = socket.AF_INET if tcp else socket.AF_UNIX
        with socket.socket(family, socket.SOCK_STREAM) as s:
            s.settimeout(DECISION_TIMEOUT)
            s.connect(tcp or BRIDGE_SOCKET)
            s.sendall((json.dumps(request) + "\n").encode())
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
        if not buf.strip():
            return {"behavior": "deny", "message": "iris: bridge closed connection"}
        return json.loads(buf.decode())
    except socket.timeout:
        return {"behavior": "deny", "message": "iris: no decision within timeout"}
    except Exception as exc:  # noqa: BLE001 - fail closed on any transport error
        log(f"bridge error: {exc!r}")
        return {"behavior": "deny", "message": f"iris: bridge unreachable ({exc})"}


def handle_tool_call(args):
    tool_name = args.get("tool_name", "")
    tool_input = args.get("input", {})
    suggestions = args.get("permission_suggestions")
    log(f"permission requested for {tool_name}")
    decision = ask_bridge(tool_name, tool_input, suggestions)

    if decision.get("behavior") == "allow":
        payload = {
            "behavior": "allow",
            "updatedInput": decision.get("updatedInput", tool_input),
        }
    else:
        payload = {
            "behavior": "deny",
            "message": decision.get("message", "Denied from iris client"),
        }
    # The permission-prompt tool answers with the decision as JSON text.
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


def respond(rid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": rid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    # Claude speaks UTF-8 on the pipe; Windows would read it as cp1252.
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method")
        rid = req.get("id")

        if method == "initialize":
            respond(rid, {
                "protocolVersion": req.get("params", {}).get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "iris-permission", "version": "1.0.0"},
            })
        elif method == "notifications/initialized":
            continue  # notification, no reply
        elif method == "tools/list":
            respond(rid, {"tools": [{
                "name": TOOL_NAME,
                "description": "Route a tool-permission decision to the iris client.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                        "input": {"type": "object"},
                        "permission_suggestions": {"type": "array"},
                    },
                    "required": ["tool_name", "input"],
                },
            }]})
        elif method == "tools/call":
            params = req.get("params", {})
            if params.get("name") != TOOL_NAME:
                respond(rid, error={"code": -32601, "message": "unknown tool"})
            else:
                respond(rid, handle_tool_call(params.get("arguments", {})))
        elif rid is not None:
            respond(rid, error={"code": -32601, "message": f"unknown method {method}"})


if __name__ == "__main__":
    main()
