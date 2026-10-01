"""Every route of the bridge, through the real handler, without Claude.

    python3 -m tests.routen

do_GET and do_POST dispatch through tables. This walks those tables over
HTTP against a stand-in session manager: each path reaches its method, and
what does not exist ends in 401, 404 or 409 rather than in the wrong
handler. tests/smoke.py covers the same routes with real sessions, but it
needs a logged-in Claude Code; this one needs nothing and runs in CI.

HOME points at a throwaway directory before the bridge is imported, so
nothing here touches the real configuration.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request

HEIM = tempfile.mkdtemp(prefix="iris-routen-")
os.environ["HOME"] = HEIM
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import config, server  # noqa: E402

TOKEN = "routen-token-nur-fuer-diesen-lauf"
ok_count = 0
fehler = []


def pruefe(bedingung, was, dazu=""):
    global ok_count
    if bedingung:
        ok_count += 1
        print(f"  ok   {was}")
    else:
        fehler.append(was)
        print(f"  FAIL {was}" + (f" ({dazu})" if dazu else ""))


class Sitzung:
    """Just what the routes call, answering yes to everything."""

    kind = "stream"

    def __init__(self, key, cwd):
        self.key, self.cwd = key, cwd
        self.claude_session_id = ""
        self.resume = ""
        self.transcript = None
        self.title = "Probe"
        self.permission_mode = "default"
        self.profile = "normal"
        self.start_offset = 0
        self.gesendet = []

    def describe(self):
        return {"key": self.key, "title": self.title}

    def open_asks(self):
        return []

    def send(self, text, attachments):
        self.gesendet.append(text)
        return True, None

    def answer_permission(self, request_id, allow, message, answers=None):
        return True, None

    def set_permission_mode(self, mode):
        if mode not in ("default", "plan"):
            return False, "unbekannter Modus"
        self.permission_mode = mode
        return True, None

    def set_model(self, model):
        return True, None

    def set_profile(self, profile):
        self.profile = profile
        return True, None

    def set_system_prompt(self, prompt):
        return (True, None) if prompt else (False, "leer")

    def control(self, subtype, payload):
        return ({"subtype": subtype}, None) if subtype else (None, "kein subtype")

    def interrupt(self):
        return True, None

    def context_usage(self):
        return {"tokens": 1}, None

    def capabilities(self):
        return {"models": []}, None


class Terminal(Sitzung):
    kind = "terminal"

    def waiting(self):
        return False

    def queued_note(self):
        return ""

    def press(self, key, text):
        return True, None


class Terminals:
    def __init__(self):
        self.sessions = {}
        self.stats = {"events": 0}
        self.away = False

    def set_away(self, away):
        self.away = away
        return away

    def handle(self, body):
        return {"seen": body.get("hook_event_name", "")}

    def get(self, key):
        return None


class Verwalter:
    def __init__(self, sitzungen):
        self.sessions = {s.key: s for s in sitzungen}
        self.terminals = Terminals()
        self.cfg = {"resident_dir": os.path.join(HEIM, "kein-bewohner")}
        self.geschlossen = []

    def get(self, key):
        return self.sessions.get(key)

    def list(self):
        return [s.describe() for s in self.sessions.values()]

    def create(self, cwd, **kw):
        if not os.path.isdir(cwd or ""):
            return None, "kein Verzeichnis"
        s = Sitzung("neu", cwd)
        self.sessions[s.key] = s
        return s, None

    def close(self, key):
        self.geschlossen.append(key)
        return self.sessions.pop(key, None) is not None


def hole(pfad, daten=None, roh=None, kopf=None, token=TOKEN):
    """One request against the test server. Returns (status, parsed body)."""
    k = {"Authorization": "Bearer " + token} if token else {}
    k.update(kopf or {})
    koerper = None
    if roh is not None:
        koerper = roh
    elif daten is not None:
        koerper = json.dumps(daten).encode()
        k["Content-Type"] = "application/json"
    anfrage = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, pfad), data=koerper,
                                     headers=k, method="POST" if koerper is not None else "GET")
    try:
        with urllib.request.urlopen(anfrage, timeout=30) as a:
            status, text = a.status, a.read()
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read()
    try:
        return status, json.loads(text)
    except ValueError:
        return status, {"_roh": len(text)}


def status(pfad, erwartet, was, daten=None, **kw):
    st, k = hole(pfad, daten, **kw)
    pruefe(st == erwartet, was, f"{st} statt {erwartet}: {k}")
    return k


# ---------- set-up ----------

ARBEIT = os.path.join(HEIM, "arbeit")
os.makedirs(ARBEIT)
SITZUNG, TERMINAL = Sitzung("s1", ARBEIT), Terminal("t1", ARBEIT)
VERWALTER = Verwalter([SITZUNG, TERMINAL, Sitzung("weg", ARBEIT)])
server.Handler.manager = VERWALTER
server.Handler.token = TOKEN
HTTP = server._Server(("127.0.0.1", 0), server.Handler)
PORT = HTTP.server_address[1]
threading.Thread(target=HTTP.serve_forever, daemon=True).start()

try:
    print("Nichts ausserhalb des Wegwerf-Ordners")
    pruefe(config.HOME == HEIM, "die Bruecke sieht nur den Wegwerf-Ordner", config.HOME)

    print("Ohne Token kommt niemand an die Schnittstelle")
    status("/api/health", 401, "GET ohne Token", token=None)
    status("/api/sessions", 401, "POST ohne Token", {"cwd": ARBEIT}, token=None)
    status("/api/heartbeat", 401, "Heartbeat mit falschem Token", {"name": "x"}, token="falsch")
    st, _ = hole("/", token=None)
    pruefe(st == 200, "die Oberflaeche selbst laedt ohne Token", str(st))

    print("GET: feste Pfade")
    pruefe(status("/api/health", 200, "health").get("ok") is True, "health meldet ok")
    status("/api/shortcuts", 200, "shortcuts")
    status("/api/commands?session=s1", 200, "commands")
    status("/api/wachen", 200, "wachen")
    status("/api/services", 200, "services")
    status("/api/services?what=token", 200, "services: Ingest-Token")
    status("/api/services?what=quatsch", 400, "services: Unbekanntes abgelehnt")
    status("/api/inventory?what=state", 200, "inventory: Zustand")
    status("/api/inventory?what=quatsch", 400, "inventory: Unbekanntes abgelehnt")
    pruefe(status("/api/git?cwd=" + ARBEIT, 200, "git").get("repo") is False,
           "git: kein Repo sauber gemeldet")
    pruefe(status("/api/git?session=s1", 200, "git ueber die Sitzung").get("repo") is False,
           "git: Verzeichnis kommt aus der Sitzung")
    status("/api/git", 400, "git: ohne Verzeichnis abgelehnt")
    status("/api/git?cwd=" + ARBEIT + "&what=quatsch", 400, "git: Unbekanntes abgelehnt")
    status("/api/config", 200, "config")
    status("/api/config/backups", 200, "config/backups")
    status("/api/profiles", 200, "profiles")
    pruefe(any(m["id"] == "plan" for m in status("/api/modes", 200, "modes")["modes"]),
           "modes kennt plan")
    status("/api/push", 200, "push")
    status("/api/hooks/stats", 200, "hooks/stats")
    status("/api/hooks/stats?session=zz", 404, "hooks/stats: unbekannte Sitzung")
    status("/api/terminals/away", 200, "terminals/away")
    status("/api/usage", 200, "usage")
    status("/api/projects", 200, "projects")
    pruefe(len(status("/api/sessions", 200, "sessions")["sessions"]) == 3, "sessions listet alle")
    status("/api/gibtsnicht", 404, "unbekannter Pfad")

    print("GET: Pfade mit wechselndem Teil")
    status("/api/resident", 404, "Bewohner, wo keiner wohnt")
    status("/api/resident/files", 404, "und seine Unterpfade genauso")
    status("/api/projects/irgendwas/sessions", 200, "Sitzungen eines Projekts")
    status("/api/projects/irgendwas", 404, "Projekt ohne /sessions")
    status("/api/ausgang/gibtsnicht", 404, "unbekannter Klotz")
    pruefe(status("/api/sessions/s1", 200, "eine Sitzung")["session"]["key"] == "s1",
           "die richtige Sitzung")
    status("/api/sessions/gibtsnicht", 404, "unbekannte Sitzung")
    status("/api/sessions/s1/quatsch", 404, "unbekannte Unteradresse")
    pruefe(status("/api/sessions/s1/history", 200, "history")["cards"] == [],
           "frische Sitzung ohne Verlauf")
    status("/api/sessions/s1/files", 200, "files")
    status("/api/sessions/s1/files/abc/diff", 200, "diff einer Datei")
    status("/api/sessions/gibtsnicht/files/abc/diff", 404, "diff: unbekannte Sitzung")
    status("/api/sessions/s1/screen", 404, "screen ohne Bildschirm")
    status("/api/sessions/s1/context", 200, "context")
    status("/api/sessions/s1/capabilities", 200, "capabilities")
    status("/api/sessions/gibtsnicht/context", 404, "context: unbekannte Sitzung")
    status("/api/sessions/s1/image?path=x.png", 404, "image, das nicht im Verlauf steht")
    status("/api/sessions/s1/media?path=x.mp3", 404, "media, das nicht im Verlauf steht")

    print("POST: feste Pfade")
    status("/api/hooks", 200, "hooks", {"hook_event_name": "Stop"})
    status("/api/eingang/schluessel", 400, "Schluessel ohne Inhalt", {})
    status("/api/ausgang/weg", 200, "ausgang/weg", {"id": "gibtsnicht"})
    status("/api/push/register", 400, "push/register ohne Token", {})
    status("/api/push/test", 409, "push/test ohne Einrichtung", {})
    pruefe(status("/api/terminals/away", 200, "terminals/away", {"away": True})["away"] is True,
           "away gesetzt")
    status("/api/services/forget", 200, "services/forget", {"id": "gibtsnicht"})
    status("/api/config/file", 400, "config/file: fremde Datei", {"path": "/etc/hosts",
                                                                  "content": "x"})
    status("/api/shortcuts", 400, "shortcuts: keine Liste", {"shortcuts": "x"})
    status("/api/shortcuts", 200, "shortcuts gespeichert", {"shortcuts": [{"label": "a",
                                                                           "text": "b"}]})
    status("/api/sessions", 201, "Sitzung angelegt", {"cwd": ARBEIT})
    status("/api/sessions", 400, "Sitzung ohne Verzeichnis", {"cwd": "/gibtsnicht"})
    status("/api/gibtsnicht", 404, "unbekannter Pfad", {})

    print("POST: Wachen")
    status("/api/wachen", 400, "Wache ohne Angaben", {})
    status("/api/wachen", 404, "Wache fuer unbekannte Sitzung",
           {"ziel": "z", "sitzung": "gibtsnicht", "vorarbeiter": "s1"})
    w = status("/api/wachen", 201, "Wache angelegt",
               {"ziel": "Probe", "sitzung": "s1", "vorarbeiter": "s1"})["wache"]
    status("/api/wachen/%s/runde" % w["id"], 200, "Runde gemeldet", {"wert": 1})
    status("/api/wachen/%s/ende" % w["id"], 200, "Wache beendet", {"grund": "Probe"})
    status("/api/wachen/gibtsnicht/runde", 404, "Runde fuer unbekannte Wache", {})
    status("/api/wachen/%s/quatsch" % w["id"], 404, "unbekannte Unteradresse", {})

    print("POST: Bewohner, wo keiner wohnt")
    status("/api/resident/stop", 404, "stop", {})
    status("/api/resident/talk", 404, "talk", {"text": "x"})
    status("/api/resident", 404, "ohne Unteradresse", {})

    print("POST: eine Sitzung")
    status("/api/sessions/s1/message", 200, "Nachricht", {"text": "hallo"})
    status("/api/sessions/s1/message", 200, "Nachricht mit Kennung", {"text": "a", "id": "m1"})
    pruefe(status("/api/sessions/s1/message", 200, "dieselbe noch einmal",
                  {"text": "a", "id": "m1"}).get("duplicate") is True,
           "Wiederholung wird erkannt")
    pruefe(SITZUNG.gesendet == ["hallo", "a"], "und nur einmal gesendet", str(SITZUNG.gesendet))
    status("/api/sessions/s1/message", 400, "leere Nachricht", {"text": " "})
    status("/api/sessions/s1/permission", 200, "Freigabe", {"request_id": "r", "allow": True})
    pruefe(status("/api/sessions/s1/mode", 200, "Modus", {"mode": "plan"})["mode"] == "plan",
           "Modus umgestellt")
    status("/api/sessions/s1/mode", 400, "unsinniger Modus", {"mode": "quatsch"})
    status("/api/sessions/s1/model", 200, "Modell", {"model": "opus"})
    status("/api/sessions/s1/profile", 200, "Profil", {"profile": "knapp"})
    status("/api/sessions/s1/system-prompt", 200, "System-Prompt", {"prompt": "p"})
    status("/api/sessions/s1/system-prompt", 400, "leerer System-Prompt", {"prompt": ""})
    status("/api/sessions/s1/control", 200, "Steuerbefehl", {"subtype": "x"})
    status("/api/sessions/s1/control", 400, "Steuerbefehl ohne subtype", {})
    pruefe(status("/api/sessions/s1/title", 200, "Titel", {"title": "Neu"})["title"] == "Neu",
           "Titel gesetzt")
    status("/api/sessions/s1/keys", 409, "Tasten nur im Terminal", {"key": "esc"})
    status("/api/sessions/s1/interrupt", 200, "Unterbrechen", {})
    status("/api/sessions/s1/quatsch", 404, "unbekannte Aktion", {})
    status("/api/sessions/gibtsnicht/message", 404, "unbekannte Sitzung", {"text": "x"})
    status("/api/sessions/s1/a/b", 404, "zu tief", {})
    status("/api/sessions/weg/close", 200, "Schliessen", {})
    pruefe(VERWALTER.geschlossen == ["weg"], "die richtige Sitzung geschlossen",
           str(VERWALTER.geschlossen))

    print("POST: Terminal-Sitzung")
    pruefe(status("/api/sessions/t1/message", 200, "Nachricht ins Terminal",
                  {"text": "x"}).get("typed") is True, "sofort eingetippt")
    status("/api/sessions/t1/keys", 200, "Tasten", {"key": "esc"})
    status("/api/sessions/t1/model", 409, "Modell geht im Terminal nicht", {"model": "x"})
    status("/api/sessions/t1/quatsch", 409, "Unbekanntes auch nicht", {})

    print("POST: Rohdaten statt JSON")
    st, k = hole("/api/sessions/s1/upload", roh=b"inhalt",
                 kopf={"X-Filename": "probe.txt", "Content-Type": "text/plain"})
    pruefe(st == 201 and "path" in k, "Hochladen", f"{st} {k}")
    st, _ = hole("/api/sessions/gibtsnicht/upload", roh=b"x", kopf={"X-Filename": "a.txt"})
    pruefe(st == 404, "Hochladen in unbekannte Sitzung", str(st))
    st, k = hole("/api/sessions/s1/eingang/gibtsnicht", roh=b"x")
    pruefe(st == 400 and not k.get("ok"), "Eingang mit unbekanntem Ticket", str(st))

finally:
    HTTP.shutdown()
    HTTP.server_close()
    shutil.rmtree(HEIM, ignore_errors=True)

print()
print(f"{ok_count} ok, {len(fehler)} fehlgeschlagen")
sys.exit(1 if fehler else 0)
