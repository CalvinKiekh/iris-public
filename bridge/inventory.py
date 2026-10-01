"""An inventory of this machine, so Claude does not have to rediscover it.

Every session otherwise starts by looking around: which projects exist, what
language, where the virtualenv is, how you run the tests, what is listening
on which port. That is the same work every time and it costs tokens on every
new conversation.

This scans once, keeps the answer in SQLite, and serves it - over HTTP for
the clients and over MCP for Claude itself.

Scanning stays deliberately shallow: project markers to a fixed depth,
skipping the directories that make a filesystem walk expensive.
"""
import json
import os
import re
import sqlite3
import subprocess
import threading
import time

from . import config

DB_PATH = os.path.join(config.CONFIG_DIR, "inventory.db")
ROOTS = [os.path.expanduser("~/Documents")]
MAX_DEPTH = 4
SKIP_DIRS = {"node_modules", ".git", "venv", ".venv", "__pycache__", "build",
             "dist", ".build", "DerivedData", ".next", "target", "vendor",
             ".mypy_cache", ".pytest_cache", "Pods", ".gradle"}

MARKERS = {
    "git": [".git"],
    "python": ["pyproject.toml", "requirements.txt", "setup.py", "Pipfile"],
    "node": ["package.json"],
    "swift": ["Package.swift"],
    "docker": ["docker-compose.yml", "docker-compose.yaml", "Dockerfile"],
    "make": ["Makefile"],
    "rust": ["Cargo.toml"],
    "go": ["go.mod"],
}

_lock = threading.Lock()


def _db():
    os.makedirs(config.CONFIG_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS projects(
        path TEXT PRIMARY KEY, name TEXT, kinds TEXT,
        git_remote TEXT, git_account TEXT, git_branch TEXT,
        commands TEXT, modified REAL, scanned REAL);
      CREATE TABLE IF NOT EXISTS envs(
        path TEXT PRIMARY KEY, project TEXT, kind TEXT,
        version TEXT, packages INTEGER, size INTEGER, scanned REAL);
      CREATE TABLE IF NOT EXISTS services(
        port INTEGER, address TEXT, proc TEXT, pid INTEGER, scanned REAL,
        PRIMARY KEY(port, address));
      CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
    """)
    return con


# ---------- scanning ----------

def _walk(root, depth=0):
    """Yield directories that look like a project, without descending into them."""
    if depth > MAX_DEPTH:
        return
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    names = {e.name for e in entries}
    hit = [kind for kind, marks in MARKERS.items() if names & set(marks)]
    if hit:
        yield root, hit
        # A project may hold sub-projects, but not below its own build output.
    for e in entries:
        if not e.is_dir(follow_symlinks=False) or e.name in SKIP_DIRS \
                or e.name.startswith("."):
            continue
        yield from _walk(e.path, depth + 1)


def _commands(path, kinds):
    """How this project is likely built, run and tested."""
    out = {}
    if "make" in kinds:
        mk = os.path.join(path, "Makefile")
        try:
            with open(mk, errors="replace") as fh:
                targets = re.findall(r"^([a-zA-Z][\w-]*):(?!=)", fh.read(), re.M)
            if targets:
                out["make"] = targets[:12]
        except OSError:
            pass
    if "node" in kinds:
        try:
            with open(os.path.join(path, "package.json"), errors="replace") as fh:
                pkg = json.load(fh)
            if isinstance(pkg.get("scripts"), dict):
                out["npm"] = list(pkg["scripts"])[:12]
        except (OSError, json.JSONDecodeError):
            pass
    if "python" in kinds:
        for f in ("pyproject.toml", "requirements.txt"):
            if os.path.exists(os.path.join(path, f)):
                out.setdefault("python", []).append(f)
    return out


def _git_info(path):
    def run(*a):
        try:
            r = subprocess.run(["git", *a], cwd=path, capture_output=True,
                               text=True, timeout=6)
            return r.stdout.strip() if r.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""
    remote = run("remote", "get-url", "origin")
    account = ""
    if "github.com" in remote:
        tail = remote.split("github.com")[-1].lstrip(":/")
        account = tail.split("/")[0] if "/" in tail else ""
    return remote, account, run("rev-parse", "--abbrev-ref", "HEAD")


def _venvs(project):
    """Virtualenvs belonging to a project, with their Python version."""
    found = []
    for name in ("venv", ".venv", "env"):
        d = os.path.join(project, name)
        cfg = os.path.join(d, "pyvenv.cfg")
        if not os.path.isfile(cfg):
            continue
        version, packages, size = "", 0, 0
        try:
            with open(cfg, errors="replace") as fh:
                for line in fh:
                    if line.lower().startswith("version"):
                        version = line.split("=")[-1].strip()
        except OSError:
            pass
        site = None
        lib = os.path.join(d, "lib")
        if os.path.isdir(lib):
            for py in os.listdir(lib):
                cand = os.path.join(lib, py, "site-packages")
                if os.path.isdir(cand):
                    site = cand
                    break
        if site:
            try:
                packages = sum(1 for n in os.listdir(site)
                               if n.endswith(".dist-info"))
            except OSError:
                pass
        try:
            size = int(subprocess.run(["du", "-sk", d], capture_output=True,
                                      text=True, timeout=20).stdout.split()[0]) * 1024
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            pass
        found.append({"path": d, "kind": "venv", "version": version,
                      "packages": packages, "size": size})
    return found


def scan_services():
    """What is listening right now - answers 'is my dev server still up'."""
    rows = []
    try:
        r = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return rows
    for line in r.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        addr = parts[8]
        if ":" not in addr:
            continue
        host, _, port = addr.rpartition(":")
        if not port.isdigit():
            continue
        rows.append({"port": int(port), "address": host or "*",
                     "proc": parts[0], "pid": int(parts[1]) if parts[1].isdigit() else 0})
    return rows


# Scanning the whole tree takes the better part of a minute, so it never
# runs in the foreground. A full sweep happens in a worker thread; the cheap
# parts (services, a single project) refresh on demand.

_state = {"running": False, "started": 0.0, "phase": "", "last": None}


def state():
    return dict(_state)


def scan_async(roots=None, on_done=None):
    """Kick off a full sweep in the background. Returns False if one runs."""
    if _state["running"]:
        return False
    _state.update(running=True, started=time.time(), phase="Projekte")

    def work():
        try:
            result = scan(roots)
            _state["last"] = result
        except Exception as exc:            # noqa: BLE001 - never kill the thread
            _state["last"] = {"error": str(exc)}
        finally:
            _state.update(running=False, phase="")
            if on_done:
                try:
                    on_done(_state["last"])
                except Exception:           # noqa: BLE001
                    pass
    threading.Thread(target=work, daemon=True).start()
    return True


def refresh_project(path):
    """Re-read one project. Cheap enough to call whenever a session ends."""
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        with _lock:
            con = _db()
            with con:
                con.execute("DELETE FROM projects WHERE path=?", (path,))
                con.execute("DELETE FROM envs WHERE project=?", (path,))
            con.close()
        return {"removed": path}

    names = set(os.listdir(path)) if os.path.isdir(path) else set()
    kinds = [k for k, marks in MARKERS.items() if names & set(marks)]
    if not kinds:
        return {"skipped": path, "reason": "kein Projekt"}

    remote, account, branch = _git_info(path) if "git" in kinds else ("", "", "")
    now = time.time()
    row = {"path": path, "name": os.path.basename(path),
           "kinds": ",".join(sorted(kinds)),
           "git_remote": remote, "git_account": account, "git_branch": branch,
           "commands": json.dumps(_commands(path, kinds), ensure_ascii=False),
           "modified": os.path.getmtime(path), "scanned": now}
    envs_rows = [{**e, "project": path, "scanned": now} for e in _venvs(path)]
    with _lock:
        con = _db()
        with con:
            con.execute(
                "INSERT OR REPLACE INTO projects VALUES"
                "(:path,:name,:kinds,:git_remote,:git_account,:git_branch,"
                ":commands,:modified,:scanned)", row)
            con.execute("DELETE FROM envs WHERE project=?", (path,))
            con.executemany(
                "INSERT OR REPLACE INTO envs VALUES"
                "(:path,:project,:kind,:version,:packages,:size,:scanned)",
                envs_rows)
        con.close()
    return {"updated": path, "kinds": kinds, "envs": len(envs_rows)}


def stale(max_age=86400):
    """Is the inventory old enough to be worth re-reading?"""
    age = time.time() - last_scan()
    return age > max_age, age


def scan(roots=None):
    """Full sweep. Returns a short summary."""
    started = time.time()
    roots = roots or ROOTS
    projects, envs = [], []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for path, kinds in _walk(root):
            _state["phase"] = os.path.basename(path)
            remote, account, branch = _git_info(path) if "git" in kinds else ("", "", "")
            try:
                modified = os.path.getmtime(path)
            except OSError:
                modified = 0
            projects.append({
                "path": path, "name": os.path.basename(path),
                "kinds": ",".join(sorted(kinds)),
                "git_remote": remote, "git_account": account, "git_branch": branch,
                "commands": json.dumps(_commands(path, kinds), ensure_ascii=False),
                "modified": modified, "scanned": started,
            })
            for e in _venvs(path):
                envs.append({**e, "project": path, "scanned": started})

    services = scan_services()
    with _lock:
        con = _db()
        with con:
            con.execute("DELETE FROM projects")
            con.executemany(
                "INSERT OR REPLACE INTO projects VALUES"
                "(:path,:name,:kinds,:git_remote,:git_account,:git_branch,"
                ":commands,:modified,:scanned)", projects)
            con.execute("DELETE FROM envs")
            con.executemany(
                "INSERT OR REPLACE INTO envs VALUES"
                "(:path,:project,:kind,:version,:packages,:size,:scanned)", envs)
            con.execute("DELETE FROM services")
            con.executemany(
                "INSERT OR REPLACE INTO services VALUES"
                "(:port,:address,:proc,:pid,:scanned)",
                [{**s, "scanned": started} for s in services])
            con.execute("INSERT OR REPLACE INTO meta VALUES('last_scan',?)",
                        (str(started),))
        con.close()
    return {"projects": len(projects), "envs": len(envs),
            "services": len(services), "seconds": round(time.time() - started, 1)}


# ---------- queries ----------

def _rows(sql, args=()):
    with _lock:
        con = _db()
        try:
            return [dict(r) for r in con.execute(sql, args).fetchall()]
        finally:
            con.close()


def last_scan():
    r = _rows("SELECT value FROM meta WHERE key='last_scan'")
    return float(r[0]["value"]) if r else 0.0


def projects(kind=None, account=None, limit=200):
    sql = "SELECT * FROM projects"
    where, args = [], []
    if kind:
        where.append("kinds LIKE ?")
        args.append(f"%{kind}%")
    if account:
        where.append("git_account = ?")
        args.append(account)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY modified DESC LIMIT ?"
    args.append(int(limit))
    rows = _rows(sql, args)
    for r in rows:
        try:
            r["commands"] = json.loads(r["commands"] or "{}")
        except json.JSONDecodeError:
            r["commands"] = {}
        r["kinds"] = [k for k in (r["kinds"] or "").split(",") if k]
    return rows


def envs(project=None):
    if project:
        return _rows("SELECT * FROM envs WHERE project=? ORDER BY path", (project,))
    return _rows("SELECT * FROM envs ORDER BY size DESC")


def services(refresh=False):
    if refresh:
        rows = scan_services()
        with _lock:
            con = _db()
            with con:
                con.execute("DELETE FROM services")
                con.executemany(
                    "INSERT OR REPLACE INTO services VALUES"
                    "(:port,:address,:proc,:pid,:scanned)",
                    [{**s, "scanned": time.time()} for s in rows])
            con.close()
        return rows
    return _rows("SELECT * FROM services ORDER BY port")


def search(term, limit=40):
    """One box that finds a project by name, path, remote or command.

    Ranked, not just filtered: an exact name beats a name that contains the
    term, which beats a match somewhere in the path. Without that, searching
    for a short name buries it under everything that merely lives near it.
    """
    like = f"%{term}%"
    rows = _rows(
        "SELECT *, CASE "
        "  WHEN LOWER(name) = LOWER(?) THEN 0 "
        "  WHEN LOWER(name) LIKE LOWER(?) THEN 1 "
        "  WHEN LOWER(git_remote) LIKE LOWER(?) THEN 2 "
        "  ELSE 3 END AS rank "
        "FROM projects WHERE name LIKE ? OR path LIKE ? "
        "OR git_remote LIKE ? OR commands LIKE ? "
        "ORDER BY rank, modified DESC LIMIT ?",
        (term, like, like, like, like, like, like, int(limit)))
    for r in rows:
        try:
            r["commands"] = json.loads(r["commands"] or "{}")
        except json.JSONDecodeError:
            r["commands"] = {}
        r["kinds"] = [k for k in (r["kinds"] or "").split(",") if k]
    return rows


def summary():
    p = _rows("SELECT COUNT(*) n FROM projects")[0]["n"]
    e = _rows("SELECT COUNT(*) n, COALESCE(SUM(size),0) s FROM envs")[0]
    s = _rows("SELECT COUNT(*) n FROM services")[0]["n"]
    by_kind = _rows("SELECT kinds, COUNT(*) n FROM projects GROUP BY kinds")
    accounts = _rows("SELECT git_account a, COUNT(*) n FROM projects "
                     "WHERE git_account<>'' GROUP BY git_account")
    return {"projects": p, "envs": e["n"], "env_bytes": e["s"],
            "services": s, "last_scan": last_scan(),
            "by_kind": by_kind, "accounts": accounts}
