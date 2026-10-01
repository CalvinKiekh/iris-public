"""iris' own file snapshots, because Claude Code's are not available here.

Claude Code keeps versioned copies under ~/.claude/file-history, but only for
interactive terminal sessions - a print-mode session like ours produces
nothing (measured, see docs/WAS-CLAUDE-LIEFERT.md). Without this module a
workstation client could show diffs for resumed terminal conversations and
nothing at all for sessions iris started itself.

The hook point is the permission broker: it sees every tool call *before* it
runs, and for Edit/Write/NotebookEdit it knows the path. That is exactly the
moment to copy the old version aside.

What this does not catch: files changed by a shell command. Bash gets no
path to snapshot, and scanning the working directory before every call would
cost more than it is worth. Those changes still show up in the tool output,
just not as a diff.
"""
import difflib
import hashlib
import os
import shutil
import time

from . import config

ROOT = os.path.join(config.CONFIG_DIR, "snapshots")
MAX_FILE = 2_000_000            # do not copy something enormous aside

# Tools whose input names a file we can snapshot.
PATH_FIELDS = {
    "Edit": "file_path",
    "Write": "file_path",
    "NotebookEdit": "notebook_path",
}


def _key(path):
    return hashlib.sha256(path.encode()).hexdigest()[:16]


def _dir(session_key):
    return os.path.join(ROOT, session_key)


def before_tool(session_key, tool_name, tool_input):
    """Snapshot a file about to be changed. Safe to call for every tool."""
    field = PATH_FIELDS.get(tool_name)
    if not field or not isinstance(tool_input, dict):
        return
    path = tool_input.get(field)
    if not path or not isinstance(path, str):
        return

    d = _dir(session_key)
    key = _key(path)
    meta = os.path.join(d, f"{key}.path")
    try:
        os.makedirs(d, exist_ok=True)
        # Remember the real path once, so diffs can be labelled later.
        if not os.path.exists(meta):
            with open(meta, "w") as fh:
                fh.write(path)
        versions = _versions(d, key)
        if not versions:
            # v0 is the state before iris touched it. A file that does not
            # exist yet gets an empty v0, so "created" shows as a clean add.
            dst = os.path.join(d, f"{key}@v0")
            if os.path.isfile(path) and os.path.getsize(path) <= MAX_FILE:
                shutil.copy2(path, dst)
            else:
                open(dst, "w").close()
    except OSError:
        pass                    # tracking must never break a tool call


def after_turn(session_key):
    """Store the current state of every tracked file as a new version."""
    d = _dir(session_key)
    if not os.path.isdir(d):
        return
    try:
        keys = {n[:-5] for n in os.listdir(d) if n.endswith(".path")}
    except OSError:
        return
    for key in keys:
        path = _path_of(d, key)
        if not path or not os.path.isfile(path):
            continue
        try:
            if os.path.getsize(path) > MAX_FILE:
                continue
            versions = _versions(d, key)
            nxt = (max(versions) + 1) if versions else 0
            latest = os.path.join(d, f"{key}@v{max(versions)}") if versions else None
            # Skip if nothing actually changed since the last snapshot.
            if latest and _same(latest, path):
                continue
            shutil.copy2(path, os.path.join(d, f"{key}@v{nxt}"))
        except OSError:
            continue


def _same(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def _versions(d, key):
    try:
        return sorted(int(n.split("@v")[1]) for n in os.listdir(d)
                      if n.startswith(key + "@v"))
    except (OSError, ValueError):
        return []


def _path_of(d, key):
    try:
        with open(os.path.join(d, f"{key}.path")) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def list_files(session_key):
    d = _dir(session_key)
    if not os.path.isdir(d):
        return []
    rows = []
    for name in os.listdir(d):
        if not name.endswith(".path"):
            continue
        key = name[:-5]
        path = _path_of(d, key)
        versions = _versions(d, key)
        if not versions:
            continue
        newest = os.path.join(d, f"{key}@v{versions[-1]}")
        rows.append({
            "id": key,
            "path": path,
            "name": os.path.basename(path),
            "versions": versions,
            "changed": os.path.getmtime(newest) if os.path.exists(newest) else 0,
            "exists": os.path.isfile(path),
            "source": "iris",
        })
    rows.sort(key=lambda r: r["changed"], reverse=True)
    return rows


def diff(session_key, file_id, frm=None, to=None):
    d = _dir(session_key)
    versions = _versions(d, file_id)
    path = _path_of(d, file_id)
    if not versions:
        return {"error": "keine Aufzeichnung für diese Datei"}

    frm = int(frm) if frm is not None else versions[0]
    old_p = os.path.join(d, f"{file_id}@v{frm}")
    if to is not None:
        new_p, new_label = os.path.join(d, f"{file_id}@v{int(to)}"), f"v{to}"
    else:
        new_p, new_label = path, "jetzt"

    def read(p, missing_is_empty=False):
        try:
            with open(p, errors="replace") as fh:
                return fh.read()
        except FileNotFoundError:
            # A file that never came into being - or was deleted again -
            # reads as empty, so the diff shows the whole thing as removed
            # rather than failing.
            return "" if missing_is_empty else None
        except OSError:
            return None

    old, new = read(old_p), read(new_p, missing_is_empty=True)
    if old is None or new is None:
        return {"error": "Version nicht lesbar", "versions": versions}

    lines = list(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"v{frm}", tofile=new_label, n=3))
    return {
        "path": path, "name": os.path.basename(path),
        "from": f"v{frm}", "to": new_label, "versions": versions,
        "added": sum(1 for l in lines if l.startswith("+") and not l.startswith("+++")),
        "removed": sum(1 for l in lines if l.startswith("-") and not l.startswith("---")),
        "diff": "".join(lines), "source": "iris",
        "exists": os.path.isfile(path),
    }


def forget(session_key):
    shutil.rmtree(_dir(session_key), ignore_errors=True)
