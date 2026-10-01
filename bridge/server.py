"""HTTP + Server-Sent-Events front end for the bridge.

SSE rather than WebSockets on purpose: it is plain HTTP, reconnects on its
own, survives the flaky links a headset lives on, and every client platform
can speak it without a library - which matters while the RayNeo SDK does not
exist yet.

Auth is a single bearer token, and the server binds to the tailnet address,
never 0.0.0.0.
"""
import collections
import json
import sys
import os
import queue
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import aktualisieren, commands, config, configs, files, maschine, names, power, heartbeat, history, inventory, live, projects, push, repos, resident as resident_mod, session as session_mod, shortcuts, tone, tracking, transfer, uploads, usage, vorarbeiter, wachen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")
# The simulator is a separate system, served alongside rather than from
# inside the app, so it can be lifted out and used for other glasses apps.
SIM_DIR = os.path.join(ROOT, "sim")
MIME = {".html": "text/html; charset=utf-8", ".js": "application/javascript",
        ".css": "text/css", ".json": "application/json",
        ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml",
        ".png": "image/png", ".ico": "image/x-icon",
        ".woff2": "font/woff2"}


IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".heic": "image/heic"}
AUDIO_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav", ".aac": "audio/aac"}


def session_image(s, path, types=None):
    """(bytes, media type) of an image this session read - or, with the
    audio types, a sound it handed over - or (None, why). The path must be
    one the session's transcript names: nothing else on this computer can be
    fetched this way."""
    types = types or IMAGE_TYPES
    ext = os.path.splitext(path or "")[1].lower()
    if ext not in types:
        return None, "kein Bild" if types is IMAGE_TYPES else "nicht abspielbar"
    sid = getattr(s, "claude_session_id", None) or getattr(s, "resume", None)
    transcript = history.find_transcript(sid) if sid else None
    if not transcript:
        return None, "kein Transcript"
    # Gesucht wird der Pfad so, wie das Transkript ihn nennt - also so, wie
    # Claude ihn geschrieben hat. Das ist oft ein relativer: ein Read auf
    # "preview/out/live_marker.png" steht genau so da.
    needle = json.dumps(path, ensure_ascii=False)
    found = False
    with open(transcript, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if needle in line:
                found = True
                break
    # Auf der Platte nachgeschlagen wird mit dem vollen Pfad. Ohne das
    # antwortete der Endpunkt auf jedes relativ gelesene Bild mit 404, und
    # in der App blieb an seiner Stelle ein leerer Kasten stehen.
    voll = path if os.path.isabs(path) else \
        os.path.normpath(os.path.join(getattr(s, "cwd", "") or "", path))
    if not found or not os.path.isfile(voll):
        return None, "Bild nicht gefunden"
    if os.path.getsize(voll) > 15 * 1024 * 1024:
        return None, "Bild zu groß"
    with open(voll, "rb") as fh:
        return fh.read(), types[ext]


# Ein Token in der Adresse (die Weboberflaeche schickt es so, weil ein
# EventSource keine Kopfzeilen setzen kann) darf nie ins Protokoll. Die Zeile
# selbst bleibt - sie ist, wofuer das Protokoll da ist -, nur das Token nicht.
_TOKEN_IN_ADRESSE = re.compile(r"((?:token|ingest_token)=)[^&\s\"']+")


def _ohne_token(text):
    return _TOKEN_IN_ADRESSE.sub(r"\1<verborgen>", text)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    manager = None
    token = ""

    def log_message(self, fmt, *args):
        """Eine Zeile je Anfrage, mit Status.

        Hier stand `pass`. Die Folge, gemessen von der PC-Seite am 13.09.:
        Die Bruecke lieferte auf `/` einen 404, weil `web/` dort fehlte - die
        App lud auf iPhone und Mac gar nicht erst. Im Log stand dazu NICHTS,
        und der Fehler war nur ueber einen Quervergleich mit der anderen
        Bruecke zu finden. Ein stiller 404 ist schlimmer als ein lauter.

        Nicht jede Anfrage: Die Kartenstroeme stehen minutenlang offen und
        die Oberflaeche holt sich im Sekundentakt Kleinigkeiten. Was 200 gibt
        und ein Abruf ist, bleibt still; alles andere steht da.
        """
        try:
            text = fmt % args
        except (TypeError, ValueError):
            text = str(fmt)
        if ' 200 ' in text or ' 204 ' in text:
            return
        print("HTTP " + _ohne_token(text), flush=True)

    def log_error(self, fmt, *args):
        """Abgebrochene Verbindungen sind kein Fehler.

        Der Klient geht weg - das Telefon sperrt den Bildschirm, ein Strom
        wird geschlossen. Im Log standen dafuer 1686 ConnectionResetError und
        931 ConnectionAbortedError als Tracebacks, zwischen denen der eine
        AttributeError nicht mehr zu sehen war, auf den es ankam.
        """
        try:
            text = fmt % args
        except (TypeError, ValueError):
            text = str(fmt)
        if any(w in text for w in ("10053", "10054", "Connection reset",
                                   "Broken pipe", "abgebrochen")):
            return
        print("HTTP-Fehler " + _ohne_token(text), flush=True)

    # ---------- helpers ----------

    def _authed_ingest(self):
        """Heartbeats use their own token.

        That token ends up on every Pi and robot, so it must not be able to
        read sessions or start anything. The full token works too, so a
        client that already has it does not need a second one.
        """
        got = ""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            got = auth[7:]
        if not got:
            got = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        if not got:
            return False
        return (secrets.compare_digest(got, heartbeat.ingest_token())
                or secrets.compare_digest(got, self.token))

    def _authed(self):
        want = self.token
        got = ""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            got = auth[7:]
        if not got:
            got = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        return bool(want) and secrets.compare_digest(got, want)

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return {}

    def _static(self, path):
        if path.startswith("/sim"):
            rel = path[len("/sim"):].lstrip("/") or "index.html"
            base, full = SIM_DIR, os.path.normpath(os.path.join(SIM_DIR, rel))
        else:
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            base, full = WEB_DIR, os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(base) or not os.path.isfile(full):
            return self._json({"error": "not found"}, 404)
        with open(full, "rb") as fh:
            data = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(os.path.splitext(full)[1],
                                                  "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        # The UI is edited constantly and served from disk each time; a
        # cached copy means changes appear to have no effect, which costs
        # far more than the bytes saved.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ---------- routing ----------

    def do_GET(self):
        u = urlparse(self.path)
        p, q = u.path, parse_qs(u.query)

        # The shell and its assets load without a token; the API does not.
        if not p.startswith("/api/"):
            return self._static(p)
        if not self._authed():
            return self._json({"error": "unauthorized"}, 401)

        route = self.GET_ROUTEN.get(p)
        if route:
            return route(self, q)
        for prefix, route in self.GET_PRAEFIXE:
            if p.startswith(prefix):
                return route(self, p[len(prefix):], q)
        return self._json({"error": "not found"}, 404)

    # ---------- GET: fixed paths ----------

    def _get_health(self, q):
        return self._json({"ok": True, "sessions": len(self.manager.sessions),
                           "name": config.machine_name(), "platform": sys.platform,
                           "power": power.state,
                           "resident": self._resident().present(),
                           # Can this bridge reach the phone at all? Without
                           # this, a missing key stays invisible until an
                           # approval waits for nothing (11.09.2026).
                           "push": push.configured(), "devices": len(push.devices())})

    def _get_shortcuts(self, q):
        return self._json({"shortcuts": shortcuts.load()})

    def _get_commands(self, q):
        # Slash commands for the phone's list and completion.
        sess = self.manager.get(q.get("session", [""])[0])
        return self._json({"commands": commands.for_session(sess)})

    def _get_wachen(self, q):
        # Die Wachen des Vorarbeiters. Lesbar auch fuer die App, damit
        # "wie ist der Stand?" ein Blick ist und kein Gespraech.
        nur = q.get("stand", [""])[0] == "laeuft"
        return self._json({"wachen": wachen.liste(nur_laufende=nur)})

    def _get_services(self, q):
        what = q.get("what", ["list"])[0]
        if what == "list":
            heartbeat.sweep()
            return self._json({
                "services": heartbeat.services(q.get("host", [None])[0]),
                "summary": heartbeat.summary()})
        if what == "events":
            return self._json({"events": heartbeat.events(
                q.get("service", [None])[0],
                int(q.get("limit", ["50"])[0]))})
        if what == "token":
            return self._json({"ingest_token": heartbeat.ingest_token()})
        return self._json({"error": "unbekannt: " + what}, 400)

    def _get_inventory(self, q):
        what = q.get("what", ["summary"])[0]
        if what == "summary":
            d = inventory.summary()
            st, age = inventory.stale()
            return self._json({**d, "stale": st, "age_seconds": age,
                               "scan": inventory.state()})
        if what == "projects":
            return self._json({"projects": inventory.projects(
                kind=q.get("kind", [None])[0],
                account=q.get("account", [None])[0],
                limit=int(q.get("limit", ["200"])[0]))})
        if what == "search":
            return self._json({"projects": inventory.search(
                q.get("q", [""])[0])})
        if what == "envs":
            return self._json({"envs": inventory.envs(
                q.get("project", [None])[0])})
        if what == "services":
            return self._json({"services": inventory.services(
                refresh=q.get("refresh", ["0"])[0] == "1")})
        if what == "state":
            return self._json(inventory.state())
        return self._json({"error": "unbekannt: " + what}, 400)

    def _get_git(self, q):
        # Read-only on purpose: committing and pushing go through Claude,
        # where they surface as a permission request you answer.
        cwd = q.get("cwd", [""])[0]
        if not cwd:
            key = q.get("session", [""])[0]
            sess = self.manager.get(key)
            cwd = sess.cwd if sess else ""
        if not cwd:
            return self._json({"error": "kein Verzeichnis"}, 400)
        what = q.get("what", ["status"])[0]
        if what == "status":
            return self._json(repos.status(cwd))
        if what == "log":
            return self._json({"commits": repos.log(cwd, int(q.get("limit", ["20"])[0]))})
        if what == "diff":
            return self._json(repos.diff(cwd,
                                         q.get("staged", ["0"])[0] == "1",
                                         q.get("path", [None])[0]))
        if what == "branches":
            return self._json({"branches": repos.branches(cwd)})
        if what == "pulls":
            return self._json({"pulls": repos.pulls(cwd)})
        if what == "checks":
            return self._json({"checks": repos.checks(cwd)})
        if what == "accounts":
            return self._json({"accounts": repos.accounts()})
        return self._json({"error": "unbekannt: " + what}, 400)

    def _get_config(self, q):
        proj = q.get("project", [""])[0] or None
        return self._json({"surfaces": configs.surfaces(proj),
                           "collections": configs.collections(proj)})

    def _get_config_file(self, q):
        return self._json(configs.read(q.get("path", [""])[0],
                                       q.get("project", [""])[0] or None))

    def _get_config_backups(self, q):
        return self._json({"backups": configs.backups()})

    def _get_profiles(self, q):
        return self._json({"profiles": tone.known(), "default": tone.DEFAULT})

    def _get_modes(self, q):
        return self._json({"modes": [
            {"id": m, "label": session_mod.MODE_LABELS.get(m, m)}
            for m in session_mod.PERMISSION_MODES]})

    def _get_push(self, q):
        return self._json(push.status())

    def _get_hooks_stats(self, q):
        want = q.get("session", [""])[0]
        if want:
            # What became of one session's display text, event by event.
            for s in self.manager.terminals.sessions.values():
                if s.claude_session_id.startswith(want):
                    return self._json({"text_log": list(s.text_log),
                                       "display_seen": s.display_seen})
            return self._json({"error": "unknown session"}, 404)
        return self._json(self.manager.terminals.stats)

    def _get_terminals_away(self, q):
        return self._json({"away": self.manager.terminals.away})

    def _get_usage(self, q):
        # The plan's limits, as the status lines and streams last said.
        return self._json(usage.snapshot())

    def _get_projects(self, q):
        return self._json({"projects": projects.list_projects()})

    def _get_sessions(self, q):
        return self._json({"sessions": self.manager.list()})

    def _get_aktualisieren(self, q):
        # Was ein Update täte, ohne dass etwas passiert: welche Fassung
        # liegt hier, was steht bereit, welche Sitzungen wären betroffen.
        return self._json(aktualisieren.plan(self.manager))

    # ---------- GET: paths with a part that varies ----------

    def _get_resident(self, rest, q):
        # Everything under /api/resident, the bare path included.
        r = self._resident()
        if not r.present():
            return self._json({"error": "Hier wohnt kein Bewohner"}, 404)
        route = self.BEWOHNER_ROUTEN.get(rest)
        if not route:
            return self._json({"error": "not found"}, 404)
        return route(self, r, q)

    def _get_projekt_sitzungen(self, rest, q):
        if not rest.endswith("/sessions"):
            return self._json({"error": "not found"}, 404)
        rows = projects.list_sessions(rest[:-len("/sessions")])
        path = q.get("path", [""])[0]
        if path:
            rows = live.annotate(rows, path)
        return self._json({"sessions": rows})

    def _get_ausgang(self, rest, q):
        # The sealed blob, on its way to the other machine. Streamed in
        # blocks: this is the endpoint a spreadsheet too big for GitHub
        # goes through, and holding it in memory twice helps nobody.
        pfad = transfer.ausgang_pfad(rest)
        if not pfad:
            return self._json({"error": "not found"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(os.path.getsize(pfad)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            with open(pfad, "rb") as fh:
                while True:
                    stueck = fh.read(transfer.BLOCK)
                    if not stueck:
                        break
                    self.wfile.write(stueck)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        return None

    def _get_sitzung(self, rest, q):
        # /api/sessions/<key>[/<what>]. A file's diff is the one path with
        # more below the key; everything else names the key, then what.
        if "/files/" in rest and rest.endswith("/diff"):
            key, _, file_id = rest[:-len("/diff")].partition("/files/")
            return self._get_sitzung_diff(key, file_id, q)
        key, _, what = rest.rpartition("/")
        route = self.SITZUNG_ROUTEN.get(what) if key else None
        if route:
            return route(self, key, q)
        s = self.manager.get(rest)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        return self._json({"session": s.describe(), "open_asks": s.open_asks()})

    # ---------- GET: one resident ----------

    def _bewohner_zustand(self, r, q):
        return self._json({"resident": r.state()})

    def _bewohner_events(self, r, q):
        since = int(q.get("since", [self.headers.get("Last-Event-ID") or 0])[0] or 0)
        return self._resident_events(r, since)

    def _bewohner_gespraeche(self, r, q):
        return self._json({"gespraeche": r.gespraeche()})

    def _bewohner_gespraech(self, r, q):
        g = r.gespraech(q.get("id", [""])[0])
        return self._json(g) if g else self._json(
            {"error": "Gespräch nicht gefunden"}, 404)

    def _bewohner_files(self, r, q):
        return self._json({"files": r.files()})

    def _bewohner_audio(self, r, q):
        data, kind = r.audio(q.get("path", [""])[0])
        if data is None:
            return self._json({"error": kind}, 404)
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=86400")
        self.end_headers()
        self.wfile.write(data)
        return None

    def _bewohner_selbst(self, r, q):
        return self._json(r.self_view())

    def _bewohner_memory(self, r, q):
        # What it remembers - read only; changes go in as files.
        one = q.get("id", [""])[0]
        if one:
            chain = r.memory(one)
            return self._json({"chain": chain}) if chain else self._json({"error": "Erinnerung nicht gefunden"}, 404)
        return self._json(r.memories(q.get("q", [""])[0], q.get("art", [""])[0],
                                     q.get("limit", ["80"])[0], q.get("replaced", [""])[0] == "1"))

    def _bewohner_file(self, r, q):
        text, err = r.read(q.get("path", [""])[0])
        if text is None:
            return self._json({"error": err}, 404)
        return self._json({"path": q.get("path", [""])[0], "text": text})

    # ---------- GET: one session ----------

    def _sitzung_screen(self, key, q):
        # The terminal as it is now - for a view a command opened there.
        s = self.manager.get(key)
        shown = s.screen_view() if s and hasattr(s, "screen_view") else None
        if shown is None:
            return self._json({"error": "kein Bildschirm"}, 404)
        return self._json(shown)

    def _sitzung_context(self, key, q):
        s = self.manager.get(key)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        data, err = s.context_usage()
        return self._json({"context": data, "error": err},
                          200 if data else 503)

    def _sitzung_capabilities(self, key, q):
        s = self.manager.get(key)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        data, err = s.capabilities()
        return self._json({"capabilities": data, "error": err},
                          200 if data else 503)

    def _sitzung_uebergabe(self, key, q):
        # Could this session be picked up on another machine? Reads only:
        # the repository is the transport, so what matters is whether it
        # has a GitHub remote, a pushed branch and a clean tree. Acting
        # on it stays a separate, answered decision.
        s = self.manager.get(key)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        out = repos.handover(getattr(s, "cwd", "") or "")
        pfad = getattr(s, "transcript", None) or \
            history.find_transcript(getattr(s, "claude_session_id", "") or "")
        out["verlauf"] = {"da": bool(pfad and os.path.isfile(pfad)),
                          "bytes": os.path.getsize(pfad)
                          if pfad and os.path.isfile(pfad) else 0}
        if out["ok"] and not out["verlauf"]["da"]:
            out["ok"] = False
            out["grund"] = "Kein Verlauf zum Mitnehmen"
        # What the work was done on. The stand travels through git, the
        # conditions do not: a session picked up on the Pi otherwise
        # repeats `swift build` and finds out at the error. What was
        # actually built with what, the session writes itself when the
        # handoff is triggered.
        out["maschine"] = maschine.specs()
        out["zettel"] = maschine.kurz(out["maschine"])
        return self._json(out)

    def _sitzung_image(self, key, q):
        return self._sitzung_datei(key, q, None)

    def _sitzung_media(self, key, q):
        return self._sitzung_datei(key, q, {**IMAGE_TYPES, **AUDIO_TYPES})

    def _sitzung_datei(self, key, q, types):
        # An image the session read, or a picture or sound it handed over -
        # shown and played in the conversation. Only a file whose path
        # stands in this session's own transcript.
        s = self.manager.get(key)
        data, kind = session_image(s, q.get("path", [""])[0], types) if s else (None, "unknown session")
        if data is None:
            return self._json({"error": kind}, 404)
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()
        self.wfile.write(data)
        return None

    def _sitzung_files(self, key, q):
        s = self.manager.get(key)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        # iris' own snapshots first: Claude Code writes file-history
        # only for interactive sessions, so for anything we host it is
        # the only source. A resumed terminal conversation can have both.
        rows = tracking.list_files(s.key)
        sid = s.claude_session_id or s.resume
        if sid:
            seen = {r["path"] for r in rows}
            rows += [r for r in files.list_files(sid)
                     if r["path"] not in seen]
        return self._json({"files": rows})

    def _get_sitzung_diff(self, key, file_id, q):
        s = self.manager.get(key)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        sid = s.claude_session_id or s.resume
        frm, to = q.get("from", [None])[0], q.get("to", [None])[0]
        own = tracking.diff(s.key, file_id, frm, to)
        if "error" not in own:
            return self._json(own)
        return self._json(files.diff(sid, file_id, frm, to) if sid else own)

    def _sitzung_history(self, key, q):
        s = self.manager.get(key)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        # Only a *resumed* conversation has history that predates this
        # bridge session. For a fresh one the live ring buffer already
        # holds everything, and reading the transcript too would show
        # every card twice.
        limit = int(q.get("limit", ["120"])[0])
        if getattr(s, "kind", "") == "terminal":
            # Everything up to where the live tail started; the tail
            # carries the rest, so nothing shows up twice.
            cards = history.load(s.claude_session_id, limit,
                                 until_offset=s.start_offset)
        else:
            cards = history.load(s.resume, limit) if s.resume else []
        return self._json({"cards": cards})

    def _sitzung_events(self, key, q):
        since = int(q.get("since", [self.headers.get("Last-Event-ID") or 0])[0] or 0)
        detail = q.get("detail", ["card"])[0]
        return self._events(key, since, detail)

    # One table per level: which path goes to which method. A new route is
    # a method plus a line here, not another branch in do_GET.
    GET_ROUTEN = {
        "/api/health": _get_health,
        "/api/shortcuts": _get_shortcuts,
        "/api/commands": _get_commands,
        "/api/wachen": _get_wachen,
        "/api/services": _get_services,
        "/api/inventory": _get_inventory,
        "/api/git": _get_git,
        "/api/config": _get_config,
        "/api/config/file": _get_config_file,
        "/api/config/backups": _get_config_backups,
        "/api/profiles": _get_profiles,
        "/api/modes": _get_modes,
        "/api/push": _get_push,
        "/api/hooks/stats": _get_hooks_stats,
        "/api/terminals/away": _get_terminals_away,
        "/api/usage": _get_usage,
        "/api/projects": _get_projects,
        "/api/sessions": _get_sessions,
        "/api/aktualisieren": _get_aktualisieren,
    }
    # Checked in order, after the fixed paths.
    GET_PRAEFIXE = (
        ("/api/resident", _get_resident),
        ("/api/projects/", _get_projekt_sitzungen),
        ("/api/ausgang/", _get_ausgang),
        ("/api/sessions/", _get_sitzung),
    )
    BEWOHNER_ROUTEN = {
        "": _bewohner_zustand,
        "/events": _bewohner_events,
        "/gespraeche": _bewohner_gespraeche,
        "/gespraech": _bewohner_gespraech,
        "/files": _bewohner_files,
        "/audio": _bewohner_audio,
        "/self": _bewohner_selbst,
        "/memory": _bewohner_memory,
        "/file": _bewohner_file,
    }
    SITZUNG_ROUTEN = {
        "screen": _sitzung_screen,
        "context": _sitzung_context,
        "capabilities": _sitzung_capabilities,
        "uebergabe": _sitzung_uebergabe,
        "image": _sitzung_image,
        "media": _sitzung_media,
        "files": _sitzung_files,
        "history": _sitzung_history,
        "events": _sitzung_events,
    }

    def do_POST(self):
        p = urlparse(self.path).path
        # Heartbeats are checked against the weaker ingest token.
        if p == "/api/heartbeat":
            return self._post_heartbeat()
        if not self._authed():
            return self._json({"error": "unauthorized"}, 401)

        # These two carry the file itself, not JSON, so they come before the
        # body is read.
        up = p.strip("/").split("/")
        if len(up) == 4 and up[:2] == ["api", "sessions"] and up[3] == "upload":
            return self._post_upload(up[2])
        if len(up) == 5 and up[:2] == ["api", "sessions"] and up[3] == "eingang":
            return self._post_eingang(up[2], up[4])

        body = self._body()
        route = self.POST_ROUTEN.get(p)
        if route:
            return route(self, body)
        for prefix, route in self.POST_PRAEFIXE:
            if p.startswith(prefix):
                return route(self, p[len(prefix):], body)
        return self._json({"error": "not found"}, 404)

    # ---------- POST: before the body is read ----------

    def _post_heartbeat(self):
        if not self._authed_ingest():
            return self._json({"error": "unauthorized"}, 401)
        b = self._body()
        r = heartbeat.beat(b.get("name", ""), b.get("host", ""),
                           status=b.get("status", "ok"),
                           detail=b.get("detail"),
                           version=b.get("version", ""),
                           interval=b.get("interval", 60))
        return self._json(r, 200 if r.get("ok") else 400)

    def _post_upload(self, key):
        # An upload is the file itself, not JSON: raw body, name in a header.
        if not self.manager.get(key):
            return self._json({"error": "unknown session"}, 404)
        n = int(self.headers.get("Content-Length") or 0)
        if n > uploads.MAX_BYTES:
            return self._json({"error": "Datei zu groß"}, 413)
        from urllib.parse import unquote
        r = uploads.save(key, unquote(self.headers.get("X-Filename", "")),
                         self.rfile.read(n), self.headers.get("Content-Type", ""))
        return self._json(r, 201 if "path" in r else 400)

    def _post_eingang(self, key, ticket):
        # The sealed blob itself, landing in a session's working directory.
        # Raw body like an upload, and streamed rather than read whole: this
        # is the path a 124-MB spreadsheet takes.
        s = self.manager.get(key)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        n = int(self.headers.get("Content-Length") or 0)
        if n > transfer.MAX_BYTES + transfer.BLOCK:
            return self._json({"ok": False, "grund": "Zu groß"}, 413)
        r = transfer.oeffnen(ticket, transfer.Begrenzt(self.rfile, n),
                             getattr(s, "cwd", "") or "")
        return self._json(r, 201 if r.get("ok") else 400)

    # ---------- POST: fixed paths ----------

    def _post_hooks(self, body):
        # Called by hooks/iris_hook.py from inside a Claude Code session
        # in a terminal. PreToolUse may park here until the phone answers;
        # the server is threaded, so that holds up nobody else.
        return self._json({"output": self.manager.terminals.handle(body)})

    def _post_schluessel(self, body):
        # The key arrives before its blob and waits in memory. Handing
        # back a ticket keeps the key out of the URL of the upload that
        # follows, where it would end up in every access log there is.
        r = transfer.schluessel_annehmen(body.get("sitzung", ""),
                                         body.get("name", ""),
                                         body.get("bloecke", 0),
                                         body.get("schluessel", ""))
        return self._json(r, 200 if r.get("ok") else 400)

    def _post_aktualisieren(self, body):
        # Beenden, aktualisieren, zurückholen. Läuft hier durch statt in
        # einem Hintergrundfaden: das Ganze dauert Sekunden, und ein
        # halbes Ergebnis wäre schlimmer als eine wartende Anfrage.
        return self._json(aktualisieren.lauf(self.manager))

    def _post_ausgang_weg(self, body):
        # Arrived, so the spool copy has no reason to exist. Swept on its
        # own after an hour too, for the transfers that never finish.
        transfer.ausgang_weg(body.get("id", ""))
        return self._json({"ok": True})

    def _post_push_register(self, body):
        r = push.register(body.get("token", ""), body.get("env", "sandbox"),
                          body.get("name", ""))
        return self._json(r, 200 if r.get("ok") else 400)

    def _post_push_test(self, body):
        # Synchronous on purpose: whoever tests wants Apple's answer.
        if not push.configured():
            return self._json({"error": "Push ist nicht eingerichtet"}, 409)
        return self._json({"results": push.deliver({
            "aps": {"alert": {"title": "iris", "subtitle": "Probe",
                              "body": "Mitteilungen kommen an."}, "sound": "default"},
            "iris": {"kind": "test"}})})

    def _post_terminals_away(self, body):
        return self._json({"away": self.manager.terminals.set_away(
            bool(body.get("away")))})

    def _post_services_forget(self, body):
        return self._json(heartbeat.forget(body.get("id", "")))

    def _post_inventory_scan(self, body):
        # Full sweeps take the better part of a minute, so this returns
        # immediately and the client watches ?what=state.
        path = body.get("project")
        if path:
            return self._json(inventory.refresh_project(path))
        started = inventory.scan_async()
        return self._json({"started": started, "state": inventory.state()},
                          202 if started else 409)

    def _post_config_file(self, body):
        r = configs.write(body.get("path", ""), body.get("content", ""),
                          body.get("project") or None)
        return self._json(r, 200 if r.get("ok") else 400)

    def _post_wachen(self, body):
        ziel = (body.get("ziel") or "").strip()
        sitzung = (body.get("sitzung") or "").strip()
        # Nicht `vorarbeiter` nennen: derselbe Name ist in dieser Datei
        # das Modul, und eine Zuweisung macht ihn fuer die ganze Funktion
        # lokal - der Aufruf weiter oben lief danach in einen
        # UnboundLocalError, und die Bruecke antwortete gar nicht mehr.
        aufseher = (body.get("vorarbeiter") or "").strip()
        if not ziel or not sitzung or not aufseher:
            return self._json({"error": "ziel, sitzung und vorarbeiter noetig"}, 400)
        if not self.manager.get(sitzung):
            return self._json({"error": f"unbekannte Sitzung: {sitzung}"}, 404)
        return self._json({"wache": wachen.neu(
            ziel, sitzung, aufseher,
            mass=body.get("mass") or "", budget=body.get("budget") or 20)}, 201)

    def _post_shortcuts(self, body):
        rows = body.get("shortcuts")
        if not isinstance(rows, list):
            return self._json({"error": "shortcuts muss eine Liste sein"}, 400)
        shortcuts.save(rows)
        return self._json({"shortcuts": shortcuts.load()})

    def _post_sessions(self, body):
        rolle = (body.get("rolle") or "").strip()
        cwd = body.get("cwd", "")
        fortsetzen = body.get("resume")
        if rolle == "vorarbeiter" and not cwd:
            # Er bekommt sein eigenes Verzeichnis, nicht irgendeines: dort
            # steht, was fuer die Aufsicht gilt, und nichts von der Arbeit.
            cwd = vorarbeiter.raum()
            # Und er setzt fort, woran er zuletzt war.
            fortsetzen = fortsetzen or vorarbeiter.zuletzt()
        s, err = self.manager.create(
            cwd, model=body.get("model"),
            permission_mode=body.get("permission_mode"),
            resume=fortsetzen, fork=bool(body.get("fork")),
            rolle=rolle)
        if not s:
            return self._json({"error": err}, 400)
        return self._json({"session": s.describe()}, 201)

    # ---------- POST: paths with a part that varies ----------

    def _post_resident(self, what, body):
        # What the app puts into the resident's workspace.
        r = self._resident()
        if not r.present():
            return self._json({"error": "Hier wohnt kein Bewohner"}, 404)
        if what == "talk":
            gid, err = r.talk(body.get("text", ""), body.get("id"), bool(body.get("draft")),
                              body.get("zu"), body.get("von"), body.get("aufnahme"),
                              stimme=body.get("stimme"))
            return self._json({"ok": bool(gid), "id": gid, "error": err}, 200 if gid else 409)
        if what == "memory":
            ok, err = r.change_memory(body.get("id", ""), body.get("aktion", ""), body.get("text", ""))
            return self._json({"ok": ok, "error": err, "pending": r.memory_changes()}, 200 if ok else 409)
        # The rest answer alike: done or not, and the resident as it is now.
        tun = {
            "stop": lambda: r.stop(bool(body.get("on", True))),
            "wake": r.wake,
            "say": lambda: r.say(body.get("text", "")),
            "decide": lambda: r.decide(body.get("id", ""), bool(body.get("allow"))),
            "file": lambda: r.write(body.get("path", ""), body.get("text", "")),
            "eingang": lambda: r.put_in(body.get("name", ""), body.get("data", "")),
        }.get(what)
        if not tun:
            return self._json({"error": "not found"}, 404)
        ok, err = tun()
        return self._json({"ok": ok, "error": err, "resident": r.state()}, 200 if ok else 409)

    def _post_wache(self, rest, body):
        # /api/wachen/<id>/runde and /api/wachen/<id>/ende
        wid, _, what = rest.rpartition("/")
        if what == "runde":
            w = wachen.runde(wid, body.get("wert"), body.get("notiz") or "")
            if not w:
                return self._json({"error": "unbekannte Wache"}, 404)
            # Was der Vorarbeiter jetzt wissen muss, ohne nachzurechnen.
            return self._json({"wache": w, "stillstand": wachen.stillstand(w),
                               "budget_verbraucht": wachen.budget_verbraucht(w)})
        if what == "ende":
            w = wachen.beenden(wid, body.get("grund") or "")
            if not w:
                return self._json({"error": "unbekannte Wache"}, 404)
            return self._json({"wache": w})
        return self._json({"error": "not found"}, 404)

    def _post_sitzung(self, rest, body):
        # /api/sessions/<key>/<action>
        if rest.endswith("/ausgang"):
            return self._post_ausgang(rest[:-len("/ausgang")], body)
        parts = rest.rstrip("/").split("/")
        if len(parts) != 2:
            return self._json({"error": "not found"}, 404)
        key, action = parts
        s = self.manager.get(key)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        if getattr(s, "kind", "") == "terminal" and action not in self.IM_TERMINAL:
            from .terminals import NOT_POSSIBLE
            return self._json({"error": NOT_POSSIBLE}, 409)
        route = self.AKTION_ROUTEN.get(action)
        if not route:
            return self._json({"error": "not found"}, 404)
        return route(self, s, body)

    def _post_ausgang(self, key, body):
        # Seal one file for a named machine. The key comes back here and
        # nowhere else - it is not stored, not logged, not put in a card.
        s = self.manager.get(key)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        r = transfer.versiegeln(getattr(s, "cwd", "") or "", s.key,
                                body.get("ziel", ""), body.get("path", ""))
        return self._json(r, 200 if r.get("ok") else 400)

    # ---------- POST: one session ----------

    def _aktion_message(self, s, body):
        text = (body.get("text") or "").strip()
        attachments = uploads.resolve(body.get("attachments"))
        if not text and not attachments:
            return self._json({"error": "leerer Text"}, 400)
        # The phone repeats a message it could not confirm - after a
        # dropped connection the first attempt may have arrived. Its
        # id makes the repeat harmless.
        mid = str(body.get("id") or "")
        seen = s.__dict__.setdefault("_message_ids", collections.OrderedDict())
        if mid and mid in seen:
            return self._json(seen[mid], 200)
        ok, err = s.send(text, attachments)
        if ok and mid:
            seen[mid] = {"ok": True, "duplicate": True}
            while len(seen) > 500:
                seen.popitem(last=False)
        if ok and getattr(s, "kind", "") == "terminal":
            # Typed into the tab at once, or waiting - and then the
            # note says until when, so nobody waits in the dark.
            typed = not s.waiting()
            return self._json({"ok": True, "queued": not typed,
                               "typed": typed,
                               "note": s.queued_note()}, 200 if typed else 202)
        return self._json({"ok": ok, "error": err}, 200 if ok else 409)

    def _aktion_permission(self, s, body):
        ok, err = s.answer_permission(
            body.get("request_id", ""), bool(body.get("allow")),
            body.get("message", ""), answers=body.get("answers"))
        return self._json({"ok": ok, "error": err}, 200 if ok else 409)

    def _aktion_mode(self, s, body):
        ok, err = s.set_permission_mode(body.get("mode", ""))
        return self._json({"ok": ok, "error": err,
                           "mode": s.permission_mode},
                          200 if ok else 400)

    def _aktion_model(self, s, body):
        ok, err = s.set_model(body.get("model", ""))
        return self._json({"ok": ok, "error": err},
                          200 if ok else 400)

    def _aktion_profile(self, s, body):
        ok, err = s.set_profile(body.get("profile", ""))
        return self._json({"ok": ok, "error": err, "profile": s.profile},
                          200 if ok else 400)

    def _aktion_system_prompt(self, s, body):
        ok, err = s.set_system_prompt(body.get("prompt", ""))
        return self._json({"ok": ok, "error": err},
                          200 if ok else 400)

    def _aktion_control(self, s, body):
        # Raw control channel, for anything a client needs that has
        # no dedicated endpoint yet.
        data, err = s.control(body.get("subtype", ""),
                              body.get("payload") or {})
        return self._json({"response": data, "error": err},
                          200 if not err else 400)

    def _aktion_title(self, s, body):
        # A name for the session - empty gives the automatic one back.
        name = names.put(s, body.get("title", ""))
        if hasattr(s, "on_change"):
            s.on_change(s)
        return self._json({"ok": True, "title": name or s.title})

    def _aktion_keys(self, s, body):
        if not hasattr(s, "press"):
            return self._json({"error": "nur bei Terminal-Sitzungen"}, 409)
        ok, err = s.press(body.get("key", ""), body.get("text", ""))
        return self._json({"ok": ok, "error": err}, 200 if ok else 409)

    def _aktion_interrupt(self, s, body):
        # Wie beim Moduswechsel: ok UND der Grund. "Es ging nicht" ohne
        # Begruendung ist am Handy nicht von einem Fehler zu
        # unterscheiden - und meistens ist der Grund harmlos.
        ok, err = s.interrupt()
        return self._json({"ok": ok, "error": err})

    def _aktion_close(self, s, body):
        return self._json({"ok": self.manager.close(s.key)})

    POST_ROUTEN = {
        "/api/hooks": _post_hooks,
        "/api/eingang/schluessel": _post_schluessel,
        "/api/aktualisieren": _post_aktualisieren,
        "/api/ausgang/weg": _post_ausgang_weg,
        "/api/push/register": _post_push_register,
        "/api/push/test": _post_push_test,
        "/api/terminals/away": _post_terminals_away,
        "/api/services/forget": _post_services_forget,
        "/api/inventory/scan": _post_inventory_scan,
        "/api/config/file": _post_config_file,
        "/api/wachen": _post_wachen,
        "/api/shortcuts": _post_shortcuts,
        "/api/sessions": _post_sessions,
    }
    POST_PRAEFIXE = (
        ("/api/resident/", _post_resident),
        ("/api/wachen/", _post_wache),
        ("/api/sessions/", _post_sitzung),
    )
    AKTION_ROUTEN = {
        "message": _aktion_message,
        "permission": _aktion_permission,
        "mode": _aktion_mode,
        "model": _aktion_model,
        "profile": _aktion_profile,
        "system-prompt": _aktion_system_prompt,
        "control": _aktion_control,
        "title": _aktion_title,
        "keys": _aktion_keys,
        "interrupt": _aktion_interrupt,
        "close": _aktion_close,
    }
    # What a terminal session can take from the phone; the rest needs a
    # session this bridge runs itself.
    IM_TERMINAL = ("message", "permission", "interrupt", "mode", "keys", "title")

    # ---------- SSE ----------

    def _resident(self):
        return resident_mod.get(self.manager.cfg)

    def _resident_events(self, r, since):
        q, backlog = r.subscribe(since)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def write(card):
            payload = json.dumps(card, ensure_ascii=False)
            self.wfile.write(f"id: {card.get('seq','')}\ndata: {payload}\n\n".encode())
            self.wfile.flush()

        try:
            # Der Rueckstand ist fuer DIESEN Leser Geschichte, auch wenn die
            # Zeile im Augenblick ihres Entstehens frisch war.
            for card in backlog:
                write({**card, "live": False})
            # DIE GRENZE ZWISCHEN GESCHICHTE UND JETZT, ausdruecklich.
            #
            # Ohne sie kann der Leser nicht wissen, wo der Rueckstand aufhoert
            # - und die App hat geraten: Sie hielt die ERSTE Zeile fuer den
            # Rueckstand und alle weiteren fuer live. Bei jeder neuen
            # Verbindung wurden damit fuenfhundert alte Zeilen als soeben
            # geschehen behandelt; im Gespraechsmodus landeten alle alten
            # Ansprachen in der Abspielschlange, und die frische Antwort stand
            # dahinter. Am 13.09. um 19:15 hat Calvin ueber eine Minute auf
            # eine Antwort gewartet, die der Bewohner nach sechs Sekunden
            # gegeben hatte.
            write({"kind": "__live__", "seq": backlog[-1]["seq"] if backlog else 0})
            while True:
                try:
                    write(q.get(timeout=20))
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError, ValueError):
            pass
        finally:
            r.unsubscribe(q)

    def _events(self, key, since, detail="card"):
        s = self.manager.get(key)
        if not s:
            return self._json({"error": "unknown session"}, 404)
        q, backlog = s.subscribe(since, detail)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def write(card):
            payload = json.dumps(card, ensure_ascii=False)
            self.wfile.write(f"id: {card.get('seq','')}\ndata: {payload}\n\n".encode())
            self.wfile.flush()

        try:
            for card in backlog:
                write(card)
            while True:
                try:
                    write(q.get(timeout=20))
                except queue.Empty:
                    # Comment frame keeps proxies and radios from dozing off.
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError, ValueError):
            pass
        finally:
            s.unsubscribe(q)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # Without this a restart within TIME_WAIT fails to bind.
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        """Ein weggegangener Klient ist kein Fehler.

        Hier kam der Rest der 3846 Tracebacks her, die das Brueckenlog auf
        dem PC auf 5,9 MB getrieben haben: Das Telefon sperrt den Bildschirm,
        ein Kartenstrom wird geschlossen - und ThreadingHTTPServer schreibt
        dafuer einen vollen Traceback. Zwischen denen war der eine
        AttributeError, auf den es ankam, nicht mehr zu sehen.

        Alles andere steht weiterhin vollstaendig da: Ein echter Fehler in
        einer Anfrage soll auffallen.
        """
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError,
                            ConnectionAbortedError, TimeoutError)):
            return
        # Unter Windows tragen genau diese die WinError 10053/10054.
        super().handle_error(request, client_address)


# Wie lange auf die eigene Adresse gewartet wird, und in welchem Abstand.
ADRESSE_WARTEN = 180
ADRESSE_TAKT = 5

# "Die angeforderte Adresse ist in diesem Kontext ungueltig" - die Adresse
# gehoert diesem Rechner (noch) nicht. Linux 99, macOS 49, Windows 10049.
ADRESSE_FEHLT = (49, 99, 10049)


def _binde(host, port, warten=True):
    """Einen Lauscher aufsetzen - und auf die Adresse warten, wenn sie fehlt.

    Ohne das Warten starb die Bruecke beim Anmelden, wenn Tailscale seine
    Adresse noch nicht gesetzt hatte: sie band, scheiterte mit WinError
    10049 und versuchte es nie wieder. Auf dem PC hiess das, dass die
    Bruecke nach jedem Neustart einfach weg war, waehrend die geplante
    Aufgabe als "Ready" dastand und die Ursache nur im Protokoll lag.
    Gefunden am 27.09. Ein Rechner, der dauerhaft erreichbar sein soll,
    darf an einer Reihenfolge beim Hochfahren nicht scheitern.

    Der Port ist davon ausgenommen: ist der belegt, laeuft dort schon eine
    Bruecke, und darauf zu warten waere falsch.
    """
    frist = time.time() + (ADRESSE_WARTEN if warten else 0)
    gemeldet = False
    while True:
        try:
            return _Server((host, port), Handler)
        except OSError as exc:
            if exc.errno not in ADRESSE_FEHLT or time.time() >= frist:
                raise
            if not gemeldet:
                print(f"iris: {host} gehoert diesem Rechner noch nicht - "
                      f"warte bis zu {ADRESSE_WARTEN} s darauf.", flush=True)
                gemeldet = True
            time.sleep(ADRESSE_TAKT)


def serve(manager, cfg):
    """Bind the API on every configured address.

    Two listeners rather than 0.0.0.0: the tailnet address for phones and
    glasses, loopback so the machine itself can reach it. Anything else on
    the local network still cannot.

    Returns the list of servers; the first one is the primary.
    """
    Handler.manager = manager
    Handler.token = cfg["token"]
    port = int(cfg["port"])

    # Ein Platzhalter deckt Loopback schon ab. Ohne diese Ausnahme band die
    # Bruecke bei --host 0.0.0.0 zuerst alles und danach noch 127.0.0.1,
    # lief in EADDRINUSE, hielt das fuer einen fremden Prozess auf dem Port
    # und beendete sich - im Container also eine Neustartschleife, mit
    # "Port 8780 ist schon belegt" als einziger Spur auf sich selbst.
    # Gefunden am 27.09. auf dem Pi.
    ALLES = ("0.0.0.0", "", "::", "*")
    hosts = [cfg["host"]]
    if cfg.get("also_localhost", True) \
            and cfg["host"] not in ("127.0.0.1", "localhost") + ALLES:
        hosts.append("127.0.0.1")

    servers = []
    for host in hosts:
        try:
            servers.append(_binde(host, port, warten=host not in ("127.0.0.1", "localhost")))
        except OSError as exc:
            if exc.errno in (48, 98):      # EADDRINUSE on macOS / Linux
                for s in servers:
                    s.server_close()
                raise PortInUse(host, port) from None
            # A missing tailnet address must not stop the loopback listener.
            if not servers:
                raise
    return servers


class PortInUse(Exception):
    def __init__(self, host, port):
        self.host, self.port = host, port
        super().__init__(f"{host}:{port} ist belegt")
