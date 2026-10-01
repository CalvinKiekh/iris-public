"""Discover Claude Code projects and their past conversations.

Claude Code stores one directory per working directory under
~/.claude/projects, with a .jsonl transcript per session. We read those to
offer "resume where I left off" without ever writing to them.
"""
import json
import os
import re
import time

from . import config


def _cwd_from_transcript(path):
    """Read the real working directory out of a transcript.

    The directory name under ~/.claude/projects replaces both "/" and "."
    with "-", so it cannot be decoded back reliably. Every transcript record
    carries the true cwd, so we read it from there instead.
    """
    try:
        with open(path, errors="replace") as fh:
            for _ in range(200):          # cwd appears in the first records
                line = fh.readline()
                if not line:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cwd = rec.get("cwd")
                if cwd:
                    return cwd
    except OSError:
        pass
    return ""


def _first_user_text(path, limit=120):
    """Pull the first human message out of a transcript for a readable title."""
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "user":
                    continue
                content = rec.get("message", {}).get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = " ".join(c.get("text", "") for c in content
                                    if isinstance(c, dict) and c.get("type") == "text")
                else:
                    continue
                text = " ".join(text.split())
                # Skip command wrappers and injected context.
                if not text or text.startswith("<") or text.startswith("Caveat:"):
                    continue
                return text[:limit]
    except OSError:
        pass
    return ""


def list_projects():
    """Return known working directories, most recently used first."""
    root = config.CLAUDE_PROJECTS
    if not os.path.isdir(root):
        return []
    out = []
    for name in os.listdir(root):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        transcripts = [f for f in os.listdir(d) if f.endswith(".jsonl")]
        if not transcripts:
            continue
        transcripts.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)),
                         reverse=True)
        newest = os.path.getmtime(os.path.join(d, transcripts[0]))
        path = ""
        for f in transcripts:                     # newest transcript wins
            path = _cwd_from_transcript(os.path.join(d, f))
            if path:
                break
        if not path or not os.path.isdir(path):
            continue          # directory is gone; nothing to resume there
        out.append({
            "id": name,
            "path": path,
            "label": os.path.basename(path.rstrip("/")) or path,
            "exists": os.path.isdir(path),
            "sessions": len(transcripts),
            "last_used": newest,
        })
    out.sort(key=lambda p: p["last_used"], reverse=True)
    return out


def list_sessions(project_id, limit=25):
    """Return resumable conversations for one project, newest first."""
    d = os.path.join(config.CLAUDE_PROJECTS, project_id)
    if not os.path.isdir(d):
        return []
    rows = []
    for f in os.listdir(d):
        if not f.endswith(".jsonl"):
            continue
        p = os.path.join(d, f)
        try:
            st = os.stat(p)
        except OSError:
            continue
        if st.st_size == 0:
            continue
        sid = f[:-6]
        # Claude Code generates a title for most conversations; it reads far
        # better than the first prompt, which is often a pasted path.
        from . import history
        rows.append({
            "session_id": sid,
            "modified": st.st_mtime,
            "size": st.st_size,
            "title": history.ai_title(project_id, sid) or _first_user_text(p),
        })
    rows.sort(key=lambda r: r["modified"], reverse=True)
    return rows[:limit]


def project_for_path(path):
    """Encode a working directory the way Claude Code does.

    Lossy on purpose - this mirrors Claude Code's own scheme, where both
    "/" and "." collapse to "-". Use it to find a directory, never to
    reconstruct a path.
    """
    return re.sub(r"[/.]", "-", path)


def human_age(ts):
    delta = max(0, time.time() - ts)
    if delta < 3600:
        return f"vor {int(delta // 60)} min"
    if delta < 86400:
        return f"vor {int(delta // 3600)} h"
    return f"vor {int(delta // 86400)} d"
