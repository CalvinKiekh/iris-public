"""Services announce themselves; iris does not go looking for them.

Polling over SSH was the obvious approach and the wrong one: it needs a
reachable host, credentials on this machine, and it only ever learns what
was true at the moment of the poll. A service knows better than anyone
whether it is healthy, and it can say so from behind NAT without iris being
able to reach it at all.

So: a service posts a heartbeat every N seconds. If one stops arriving, the
service is reported missing after its own stated interval times a grace
factor. Nothing here reaches out to anything.

Writing a heartbeat uses a separate, weaker token than the rest of the API:
that token ends up on every Pi and robot, so it must not be able to read
sessions or start anything.
"""
import json
import os
import secrets
import sqlite3
import threading
import time

from . import config

DB_PATH = os.path.join(config.CONFIG_DIR, "heartbeat.db")
GRACE = 2.5              # missed intervals before a service counts as gone
MAX_HISTORY = 50         # state changes kept per service

_lock = threading.Lock()


def _db():
    os.makedirs(config.CONFIG_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS services(
        id TEXT PRIMARY KEY,          -- host/name
        name TEXT, host TEXT,
        status TEXT,                  -- what the service says about itself
        detail TEXT,                  -- free-form JSON from the service
        version TEXT,
        interval REAL,                -- how often it promises to report
        first_seen REAL, last_seen REAL,
        was_missing INTEGER DEFAULT 0);
      CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service TEXT, at REAL, kind TEXT, note TEXT);
      CREATE INDEX IF NOT EXISTS events_service ON events(service, at DESC);
    """)
    return con


def ingest_token():
    """A second token, only good for posting heartbeats."""
    cfg = config.load()
    if not cfg.get("ingest_token"):
        cfg["ingest_token"] = secrets.token_urlsafe(24)
        config.save(cfg)
    return cfg["ingest_token"]


def beat(name, host, *, status="ok", detail=None, version="", interval=60.0):
    """Record one heartbeat. Everything but name and host is optional."""
    name = (name or "").strip()[:80]
    host = (host or "").strip()[:80]
    if not name or not host:
        return {"error": "name und host sind nötig"}
    sid = f"{host}/{name}"
    now = time.time()
    try:
        interval = max(5.0, min(float(interval), 86400.0))
    except (TypeError, ValueError):
        interval = 60.0

    with _lock:
        con = _db()
        try:
            prev = con.execute("SELECT status, was_missing FROM services "
                               "WHERE id=?", (sid,)).fetchone()
            with con:
                con.execute(
                    "INSERT INTO services"
                    "(id,name,host,status,detail,version,interval,"
                    " first_seen,last_seen,was_missing)"
                    " VALUES(?,?,?,?,?,?,?,?,?,0)"
                    " ON CONFLICT(id) DO UPDATE SET"
                    "  status=excluded.status, detail=excluded.detail,"
                    "  version=excluded.version, interval=excluded.interval,"
                    "  last_seen=excluded.last_seen, was_missing=0",
                    (sid, name, host, status,
                     json.dumps(detail or {}, ensure_ascii=False),
                     version, interval, now, now))
                # Only note something when the state actually changed - a
                # log of "still fine" every minute helps nobody.
                if prev is None:
                    _event(con, sid, "erschienen", "")
                elif prev["was_missing"]:
                    _event(con, sid, "zurück", "")
                elif prev["status"] != status:
                    _event(con, sid, "zustand", f"{prev['status']} → {status}")
        finally:
            con.close()
    return {"ok": True, "id": sid, "expected_within": interval * GRACE}


def _event(con, sid, kind, note):
    con.execute("INSERT INTO events(service,at,kind,note) VALUES(?,?,?,?)",
                (sid, time.time(), kind, note))
    con.execute("DELETE FROM events WHERE service=? AND id NOT IN "
                "(SELECT id FROM events WHERE service=? ORDER BY at DESC LIMIT ?)",
                (sid, sid, MAX_HISTORY))


def sweep():
    """Mark services whose heartbeat stopped. Call periodically."""
    now = time.time()
    with _lock:
        con = _db()
        try:
            gone = con.execute(
                "SELECT id, name, host, interval, last_seen FROM services "
                "WHERE was_missing=0 AND (? - last_seen) > interval * ?",
                (now, GRACE)).fetchall()
            with con:
                for r in gone:
                    con.execute("UPDATE services SET was_missing=1 WHERE id=?",
                                (r["id"],))
                    silent = int(now - r["last_seen"])
                    _event(con, r["id"], "vermisst", f"seit {silent}s still")
            return [dict(r) for r in gone]
        finally:
            con.close()


def _row(r, now):
    detail = {}
    try:
        detail = json.loads(r["detail"] or "{}")
    except json.JSONDecodeError:
        pass
    silent = now - r["last_seen"]
    missing = bool(r["was_missing"]) or silent > r["interval"] * GRACE
    return {
        "id": r["id"], "name": r["name"], "host": r["host"],
        "status": "vermisst" if missing else r["status"],
        "reported_status": r["status"],
        "missing": missing,
        "detail": detail, "version": r["version"],
        "interval": r["interval"],
        "last_seen": r["last_seen"], "silent_for": round(silent, 1),
        "first_seen": r["first_seen"],
    }


def services(host=None, include_gone=True):
    now = time.time()
    with _lock:
        con = _db()
        try:
            if host:
                rows = con.execute("SELECT * FROM services WHERE host=? "
                                   "ORDER BY name", (host,)).fetchall()
            else:
                rows = con.execute("SELECT * FROM services "
                                   "ORDER BY host, name").fetchall()
        finally:
            con.close()
    out = [_row(r, now) for r in rows]
    return out if include_gone else [s for s in out if not s["missing"]]


def events(service=None, limit=50):
    with _lock:
        con = _db()
        try:
            if service:
                rows = con.execute(
                    "SELECT * FROM events WHERE service=? ORDER BY at DESC "
                    "LIMIT ?", (service, int(limit))).fetchall()
            else:
                rows = con.execute("SELECT * FROM events ORDER BY at DESC "
                                   "LIMIT ?", (int(limit),)).fetchall()
        finally:
            con.close()
    return [dict(r) for r in rows]


def forget(service_id):
    with _lock:
        con = _db()
        try:
            with con:
                con.execute("DELETE FROM services WHERE id=?", (service_id,))
                con.execute("DELETE FROM events WHERE service=?", (service_id,))
        finally:
            con.close()
    return {"ok": True}


def summary():
    now = time.time()
    all_rows = services()
    return {
        "total": len(all_rows),
        "healthy": sum(1 for s in all_rows
                       if not s["missing"] and s["reported_status"] == "ok"),
        "unhealthy": sum(1 for s in all_rows
                         if not s["missing"] and s["reported_status"] != "ok"),
        "missing": sum(1 for s in all_rows if s["missing"]),
        "hosts": sorted({s["host"] for s in all_rows}),
        "now": now,
    }
