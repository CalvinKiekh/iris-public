"""Which files a conversation touched, and how they changed.

Claude Code keeps versioned copies of every file it edits under
~/.claude/file-history/<session-id>/<hash>@v<N>, and each transcript carries
a `file-history-snapshot` mapping those hashes to real paths. Reading both
gives real diffs - including changes made through a shell script, which
reconstructing from Edit tool inputs would miss entirely.

Read-only. Nothing here writes to a file or to the history.
"""
import difflib
import json
import os

from . import config, history

HISTORY_ROOT = os.path.join(os.path.expanduser("~"), ".claude", "file-history")
MAX_DIFF_BYTES = 400_000          # refuse to diff something enormous


def _backups(session_id):
    """hash -> {path, versions:[int], dir} for one conversation."""
    transcript = history.find_transcript(session_id)
    if not transcript:
        return {}

    tracked = {}                  # backupFileName stem -> real path
    try:
        with open(transcript, errors="replace") as fh:
            for line in fh:
                if '"file-history-snapshot"' not in line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for path, info in (rec.get("snapshot", {})
                                      .get("trackedFileBackups") or {}).items():
                    # `backupFileName` kann fehlen ODER null sein. Der
                    # Vorgabewert faengt nur das Fehlen ab; bei null kam
                    # AttributeError: 'NoneType' object has no attribute
                    # 'split', und der riss die ganze Anfrage ab - der Klient
                    # bekam RemoteDisconnected, das Log schwieg. Gemessen von
                    # der PC-Seite am 13.09. an /api/sessions/<key>/files.
                    name = info.get("backupFileName") or ""
                    if not isinstance(name, str):
                        continue
                    stem = name.split("@")[0]
                    if stem:
                        tracked[stem] = path
    except OSError:
        return {}

    d = os.path.join(HISTORY_ROOT, session_id)
    if not os.path.isdir(d):
        return {}

    out = {}
    for entry in os.listdir(d):
        stem, _, ver = entry.partition("@")
        if not ver.startswith("v") or not ver[1:].isdigit():
            continue
        row = out.setdefault(stem, {"path": tracked.get(stem, ""),
                                    "versions": [], "dir": d})
        row["versions"].append(int(ver[1:]))
    for row in out.values():
        row["versions"].sort()
    return out


def list_files(session_id):
    """Files this conversation changed, most recently changed first."""
    rows = []
    for stem, info in _backups(session_id).items():
        if not info["versions"]:
            continue
        newest = os.path.join(info["dir"], f"{stem}@v{info['versions'][-1]}")
        try:
            mtime = os.path.getmtime(newest)
        except OSError:
            mtime = 0
        path = info["path"]
        rows.append({
            "id": stem,
            "path": path,
            "name": os.path.basename(path) if path else stem,
            "versions": info["versions"],
            "changed": mtime,
            "exists": bool(path) and os.path.isfile(path),
        })
    rows.sort(key=lambda r: r["changed"], reverse=True)
    return rows


def _read(path):
    try:
        if os.path.getsize(path) > MAX_DIFF_BYTES:
            return None
        with open(path, errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def diff(session_id, file_id, frm=None, to=None):
    """Unified diff between two stored versions.

    Without `to`, compares against the file as it is on disk now - that is
    the version the user actually cares about.
    """
    info = _backups(session_id).get(file_id)
    if not info or not info["versions"]:
        return {"error": "unbekannte Datei"}

    versions = info["versions"]
    frm = int(frm) if frm else versions[0]
    old_path = os.path.join(info["dir"], f"{file_id}@v{frm}")
    old = _read(old_path)

    if to:
        new_path = os.path.join(info["dir"], f"{file_id}@v{int(to)}")
        new_label = f"v{to}"
    else:
        new_path, new_label = info["path"], "jetzt"
    new = _read(new_path) if new_path else None

    if old is None or new is None:
        return {"error": "Datei zu groß oder nicht lesbar",
                "path": info["path"], "versions": versions}

    lines = list(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"v{frm}", tofile=new_label, n=3))
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    return {
        "path": info["path"],
        "name": os.path.basename(info["path"]) if info["path"] else file_id,
        "from": f"v{frm}", "to": new_label,
        "versions": versions,
        "added": added, "removed": removed,
        "diff": "".join(lines),
    }
