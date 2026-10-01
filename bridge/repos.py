"""Read-only view of the git state a session is working in.

Deliberately read-only. Committing, pushing and opening pull requests all
change something outside this machine, so they go through Claude - where
they surface as a permission request you answer - rather than through an
HTTP endpoint that acts on its own. The API shows you what is going on;
the decision to act stays a decision.

`gh` is used only where git cannot answer (pull requests, checks).
"""
import json
import os
import time
import shutil
import subprocess

GH = shutil.which("gh")
GIT = shutil.which("git") or "/usr/bin/git"
TIMEOUT = 12


def _git(cwd, *args):
    try:
        r = subprocess.run([GIT, *args], cwd=cwd, capture_output=True,
                           text=True, timeout=TIMEOUT)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def is_repo(cwd):
    return _git(cwd, "rev-parse", "--is-inside-work-tree") == "true"


def _account_for(remote):
    """Which GitHub account owns this remote.

    Worth surfacing: work and private repositories live under different
    accounts here, and a push to the wrong one is annoying to undo.
    """
    if not remote or "github.com" not in remote:
        return ""
    tail = remote.split("github.com")[-1].lstrip(":/")
    return tail.split("/")[0] if "/" in tail else ""


def status(cwd):
    """Branch, upstream distance, and what is dirty."""
    if not is_repo(cwd):
        return {"repo": False}

    root = _git(cwd, "rev-parse", "--show-toplevel")
    branch = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    remote = _git(cwd, "remote", "get-url", "origin")
    upstream = _git(cwd, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")

    ahead = behind = 0
    if upstream:
        counts = _git(cwd, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
        parts = counts.split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])

    changes = []
    for line in _git(cwd, "status", "--porcelain=v1").splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        changes.append({
            "path": path,
            "staged": code[0] not in " ?",
            "untracked": code == "??",
            "code": code.strip(),
        })

    # Lines added and removed against the last commit - the "+18 -2" a
    # session header shows. Binary files report "-" and are left out.
    added = removed = 0
    for line in _git(cwd, "diff", "--numstat", "HEAD").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            added += int(parts[0])
            removed += int(parts[1])

    return {
        "repo": True, "root": root, "branch": branch,
        "remote": remote, "account": _account_for(remote),
        "upstream": upstream, "ahead": ahead, "behind": behind,
        "changes": changes, "dirty": bool(changes),
        "added": added, "removed": removed,
    }


# What counts as worth naming. Build output is ignored on purpose and
# nobody misses it; a spreadsheet of that size is another matter.
def _size(pfad):
    try:
        return os.path.getsize(pfad)
    except OSError:
        return 0


GROSS = 1024 * 1024
ZU_GROSS_FUER_GITHUB = 50 * 1024 * 1024
MAX_GENANNT = 8


def _ignoriert(cwd):
    """Ignored things that travel with nothing: files by size, folders by name.

    Walking the folders was tried and thrown away - three seconds spent
    inside mac/.build to report screenshots nobody misses, while the walk
    ran out of time before reaching anything else. A spreadsheet that has to
    come along sits in the working directory and is ignored by name, which
    git reports directly. Whole ignored trees are named, not measured: that
    they do not travel is the point, their size is not.
    """
    dateien, ordner = [], []
    for line in _git(cwd, "status", "--porcelain", "--ignored=matching").splitlines():
        if not line.startswith("!!"):
            continue
        rel = line[3:].strip()
        if rel.endswith("/"):
            ordner.append(rel)
            continue
        n = _size(os.path.join(cwd, rel))
        if n >= GROSS:
            dateien.append({"path": rel, "bytes": n})
    dateien.sort(key=lambda e: -e["bytes"])
    return {"dateien": dateien[:MAX_GENANNT], "ordner": sorted(ordner)[:MAX_GENANNT]}


def handover(cwd):
    """Whether this working directory could be picked up on another machine.

    Reads, decides nothing. The transfer runs over the repository: the target
    clones or pulls it, so it needs a remote on GitHub, a branch that exists
    there, and nothing lying around uncommitted. Each of those is named on its
    own, because "geht nicht" without a reason is useless from a phone.
    """
    st = status(cwd)
    if not st.get("repo"):
        return {"ok": False, "grund": "Kein Git-Repository", **st}
    remote = st.get("remote") or ""
    offen = st.get("changes") or []
    gruende = []
    if "github.com" not in remote:
        gruende.append("Kein GitHub-Remote" if remote else "Kein Remote gesetzt")
    if not st.get("upstream"):
        gruende.append("Branch ist nicht auf dem Remote")
    if offen:
        gruende.append("%d ungesicherte Datei%s" % (len(offen), "" if len(offen) == 1 else "en"))
    if st.get("ahead"):
        gruende.append("%d Commit%s noch nicht gepusht"
                       % (st["ahead"], "" if st["ahead"] == 1 else "s"))
    # Two warnings that do not stop anything, because both are yours to
    # judge: what would not travel, and what git would choke on.
    ignoriert = _ignoriert(cwd)
    schwer = [{"path": c["path"], "bytes": _size(os.path.join(cwd, c["path"]))}
              for c in offen]
    schwer = [e for e in schwer if e["bytes"] >= ZU_GROSS_FUER_GITHUB]
    return {"ok": not gruende, "grund": " · ".join(gruende),
            "ignoriert": ignoriert, "schwer": schwer, **st}


def log(cwd, limit=20):
    if not is_repo(cwd):
        return []
    fmt = "%H%x1f%h%x1f%an%x1f%ar%x1f%s"
    out = _git(cwd, "log", f"-{int(limit)}", f"--pretty=format:{fmt}")
    rows = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 5:
            rows.append({"sha": parts[0], "short": parts[1], "author": parts[2],
                         "when": parts[3], "subject": parts[4]})
    return rows


def diff(cwd, staged=False, path=None, max_bytes=300_000):
    """The working-tree diff - what would go into the next commit."""
    if not is_repo(cwd):
        return {"error": "kein Git-Repo"}
    args = ["diff"] + (["--staged"] if staged else [])
    if path:
        args += ["--", path]
    text = _git(cwd, *args)
    truncated = len(text) > max_bytes
    return {"diff": text[:max_bytes], "truncated": truncated,
            "staged": staged, "path": path or ""}


def branches(cwd, limit=30):
    if not is_repo(cwd):
        return []
    out = _git(cwd, "for-each-ref", "--sort=-committerdate",
               f"--count={int(limit)}",
               "--format=%(refname:short)%1f%(committerdate:relative)%1f%(upstream:short)",
               "refs/heads")
    rows = []
    current = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    for line in out.splitlines():
        parts = line.split("\x1f")
        if parts:
            rows.append({"name": parts[0],
                         "when": parts[1] if len(parts) > 1 else "",
                         "upstream": parts[2] if len(parts) > 2 else "",
                         "current": parts[0] == current})
    return rows


def _gh(cwd, *args):
    if not GH:
        return None
    try:
        r = subprocess.run([GH, *args], cwd=cwd, capture_output=True,
                           text=True, timeout=TIMEOUT)
        if r.returncode != 0:
            return None
        return json.loads(r.stdout) if r.stdout.strip() else None
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def pulls(cwd, limit=10):
    """Open pull requests, if this repo has a GitHub remote."""
    data = _gh(cwd, "pr", "list", "--limit", str(int(limit)), "--json",
               "number,title,author,isDraft,headRefName,url,updatedAt")
    if not data:
        return []
    return [{"number": p["number"], "title": p["title"],
             "author": (p.get("author") or {}).get("login", ""),
             "draft": p.get("isDraft", False), "branch": p.get("headRefName", ""),
             "url": p.get("url", ""), "updated": p.get("updatedAt", "")}
            for p in data]


def checks(cwd):
    """State of CI on the current branch - the 'is it still green' question."""
    data = _gh(cwd, "pr", "checks", "--json", "name,state,link")
    if not data:
        return []
    return [{"name": c.get("name", ""), "state": c.get("state", ""),
             "url": c.get("link", "")} for c in data]


def accounts():
    """Which GitHub accounts gh knows, and which one is active."""
    if not GH:
        return []
    try:
        r = subprocess.run([GH, "auth", "status"], capture_output=True,
                           text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return []
    rows, current = [], None
    for line in (r.stdout + r.stderr).splitlines():
        line = line.strip()
        if "Logged in to" in line and "account" in line:
            current = {"name": line.split("account")[-1].split("(")[0].strip(),
                       "active": False}
            rows.append(current)
        elif current is not None and line.startswith("- Active account:"):
            current["active"] = line.endswith("true")
    return rows
