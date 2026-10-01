"""Read and edit the files Claude Code reads.

A workstation client should be able to see and change what shapes a session -
settings, memory, agents, commands, CLAUDE.md - without hunting through the
filesystem. A phone almost certainly should not, which is why this is a
separate surface rather than part of the session API.

Two rules keep this from being dangerous:
  - Only known kinds of file, resolved from a fixed set of roots. No
    arbitrary path ever reaches the filesystem.
  - Every write keeps a timestamped backup first, and JSON is parsed before
    it is written. A broken settings.json can stop Claude Code from starting.
"""
import json
import os
import shutil
import time

HOME = os.path.expanduser("~")
CLAUDE_DIR = os.path.join(HOME, ".claude")
BACKUP_DIR = os.path.join(HOME, ".config", "iris", "config-backups")

# Everything editable, and where it lives. `scope` says how far it reaches.
SURFACES = [
    {"id": "user-settings",      "path": os.path.join(CLAUDE_DIR, "settings.json"),
     "label": "Einstellungen (Benutzer)", "kind": "json", "scope": "benutzer",
     "note": "Modell, Hooks, Plugins, Auto-Modus"},
    {"id": "user-settings-local", "path": os.path.join(CLAUDE_DIR, "settings.local.json"),
     "label": "Einstellungen lokal", "kind": "json", "scope": "benutzer",
     "note": "Berechtigungen (allow/deny)"},
    {"id": "user-claude-md",     "path": os.path.join(CLAUDE_DIR, "CLAUDE.md"),
     "label": "CLAUDE.md (Benutzer)", "kind": "md", "scope": "benutzer",
     "note": "gilt für alle Projekte"},
    {"id": "global-state",       "path": os.path.join(HOME, ".claude.json"),
     "label": "Globaler Zustand", "kind": "json", "scope": "benutzer",
     "note": "groß, enthält Verlaufsdaten — mit Bedacht ändern",
     "readonly": True},
]

PROJECT_SURFACES = [
    ("project-claude-md",    "CLAUDE.md",                   "CLAUDE.md (Projekt)",  "md"),
    ("project-settings",     ".claude/settings.json",       "Einstellungen (Projekt)", "json"),
    ("project-settings-local", ".claude/settings.local.json", "Einstellungen lokal (Projekt)", "json"),
    ("project-mcp",          ".mcp.json",                   "MCP-Server (Projekt)", "json"),
]

# Directories whose files are all editable of the same kind.
COLLECTIONS = [
    {"id": "agents",   "dir": os.path.join(CLAUDE_DIR, "agents"),
     "label": "Subagenten", "kind": "md", "ext": ".md"},
    {"id": "commands", "dir": os.path.join(CLAUDE_DIR, "commands"),
     "label": "Eigene Befehle", "kind": "md", "ext": ".md"},
    {"id": "memory",   "dir": None,      # resolved per project below
     "label": "Erinnerungen", "kind": "md", "ext": ".md"},
]


def memory_dir(project_path):
    """Auto-memory lives beside the project's transcripts."""
    from . import projects
    return os.path.join(os.path.expanduser("~/.claude/projects"),
                        projects.project_for_path(project_path), "memory")


def _stat(path):
    try:
        st = os.stat(path)
        return {"exists": True, "size": st.st_size, "modified": st.st_mtime}
    except OSError:
        return {"exists": False, "size": 0, "modified": 0}


def surfaces(project_path=None):
    """Everything this client could look at, with existence and size."""
    out = []
    for s in SURFACES:
        out.append({**s, **_stat(s["path"])})
    if project_path:
        # A project living in $HOME resolves to the same files as the user
        # scope; listing them twice would invite editing one and wondering
        # why the other changed.
        seen = {os.path.realpath(s["path"]) for s in out}
        for sid, rel, label, kind in PROJECT_SURFACES:
            p = os.path.join(project_path, rel)
            if os.path.realpath(p) in seen:
                continue
            out.append({"id": sid, "path": p, "label": label, "kind": kind,
                        "scope": "projekt", "note": "", **_stat(p)})
    return out


def collections(project_path=None):
    """Directories of editable files, with their contents listed."""
    out = []
    for c in COLLECTIONS:
        d = c["dir"]
        if c["id"] == "memory":
            if not project_path:
                continue
            d = memory_dir(project_path)
        items = []
        if d and os.path.isdir(d):
            for name in sorted(os.listdir(d)):
                if not name.endswith(c["ext"]):
                    continue
                p = os.path.join(d, name)
                items.append({"name": name, "path": p, **_stat(p)})
        out.append({"id": c["id"], "label": c["label"], "kind": c["kind"],
                    "dir": d, "count": len(items), "items": items})
    return out


def _allowed(path, project_path=None):
    """A path is only readable if a surface or collection names it."""
    path = os.path.realpath(path)
    for s in surfaces(project_path):
        if os.path.realpath(s["path"]) == path:
            return s
    for c in collections(project_path):
        for it in c["items"]:
            if os.path.realpath(it["path"]) == path:
                return {**c, "path": it["path"], "readonly": False}
        # A new file inside a known collection directory is allowed too.
        if c["dir"] and os.path.dirname(path) == os.path.realpath(c["dir"]) \
                and path.endswith(".md"):
            return {**c, "path": path, "readonly": False}
    return None


def read(path, project_path=None, max_bytes=2_000_000):
    s = _allowed(path, project_path)
    if not s:
        return {"error": "Diese Datei ist nicht freigegeben"}
    try:
        if os.path.getsize(path) > max_bytes:
            return {"error": "Datei zu groß", "size": os.path.getsize(path)}
        with open(path, errors="replace") as fh:
            content = fh.read()
    except OSError as exc:
        return {"error": f"nicht lesbar: {exc}"}
    return {"path": path, "label": s.get("label", ""), "kind": s.get("kind", "md"),
            "readonly": bool(s.get("readonly")), "content": content,
            **_stat(path)}


def write(path, content, project_path=None):
    s = _allowed(path, project_path)
    if not s:
        return {"error": "Diese Datei ist nicht freigegeben"}
    if s.get("readonly"):
        return {"error": "Diese Datei ist schreibgeschützt"}

    # A broken settings.json can stop Claude Code from starting, so parse first.
    if s.get("kind") == "json":
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            return {"error": f"Kein gültiges JSON: {exc}"}

    backup = ""
    if os.path.exists(path):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = os.path.join(BACKUP_DIR,
                              f"{os.path.basename(path)}.{stamp}")
        try:
            shutil.copy2(path, backup)
        except OSError as exc:
            return {"error": f"Sicherung fehlgeschlagen: {exc}"}

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".iris-tmp"
        with open(tmp, "w") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except OSError as exc:
        return {"error": f"Schreiben fehlgeschlagen: {exc}"}
    return {"ok": True, "path": path, "backup": backup, **_stat(path)}


def backups():
    """What has been overwritten, newest first."""
    if not os.path.isdir(BACKUP_DIR):
        return []
    rows = []
    for name in os.listdir(BACKUP_DIR):
        p = os.path.join(BACKUP_DIR, name)
        rows.append({"name": name, "path": p, **_stat(p)})
    rows.sort(key=lambda r: r["modified"], reverse=True)
    return rows
