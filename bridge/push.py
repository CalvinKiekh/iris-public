"""Push to the phone: what needs you reaches you, with the answer on it.

Straight to Apple's push service, no server in between. Apple insists on
HTTP/2 and an ES256-signed token; the standard library has neither, so curl
(HTTP/2 through nghttp2, shipped with macOS) and openssl do those two jobs -
the same way the bridge leans on git and lsof.

Pushed only when it helps: an approval, a question, or a long turn that
ended - and only when nobody is looking at that session, or when away is on.
A notification about something already on screen is noise.

Configured in ~/.config/iris/config.json under "push": key_path, key_id,
team_id, topic. The key is the team's APNs key; it never enters the repo.
"""
import base64
import json
import re
import os
import subprocess
import tempfile
import threading
import time

from . import config

DEVICES = os.path.join(config.CONFIG_DIR, "push-devices.json")
HOSTS = {"sandbox": "api.sandbox.push.apple.com", "production": "api.push.apple.com"}

# A turn this long is worth a note when it ends; a short one you saw finish.
DONE_AFTER = 90

TITLES = {"Write": "Datei anlegen", "Edit": "Datei ändern", "MultiEdit": "Datei ändern",
          "NotebookEdit": "Notebook ändern", "Bash": "Befehl ausführen",
          "WebFetch": "Seite abrufen", "WebSearch": "Im Netz suchen"}

_cfg = {}
_away = lambda: False                                   # noqa: E731
_lock = threading.Lock()
_jwt = (None, 0.0)
_pushed = set()             # request ids that went out - only those get taken back
last_results = []


def configure(cfg, away):
    global _cfg, _away
    # A test bridge reads the real config - key, phones and all. Without
    # this it pushed every approval its tests provoke to a real phone.
    _cfg = {} if os.environ.get("IRIS_NO_PUSH") else dict(cfg.get("push") or {})
    _away = away


def configured():
    key = os.path.expanduser(_cfg.get("key_path") or "")
    return bool(_cfg.get("key_id") and _cfg.get("team_id") and _cfg.get("topic")
                and key and os.path.isfile(key))


# ---------- devices ----------

def devices():
    try:
        with open(DEVICES) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return []


def _save(rows):
    os.makedirs(config.CONFIG_DIR, exist_ok=True)
    tmp = DEVICES + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(rows, fh, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, DEVICES)


def register(token, env, name=""):
    token = (token or "").strip().lower()
    if len(token) < 32 or any(c not in "0123456789abcdef" for c in token):
        return {"ok": False, "error": "kein gültiges Geräte-Token"}
    if env not in HOSTS:
        return {"ok": False, "error": f"unbekannte Umgebung: {env}"}
    with _lock:
        rows = [d for d in devices() if d["token"] != token]
        rows.append({"token": token, "env": env, "name": name[:60],
                     "added": time.time(), "last_ok": None})
        _save(rows)
    return {"ok": True, "devices": len(rows)}


def _update(token, **fields):
    with _lock:
        rows = devices()
        for d in rows:
            if d["token"] == token:
                d.update(fields)
        _save(rows)


def _forget(token):
    with _lock:
        _save([d for d in devices() if d["token"] != token])


# ---------- the token Apple wants ----------

def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _der_to_raw(der):
    """openssl signs in DER (SEQUENCE of two INTEGERs); JWT wants r || s."""
    i = 2
    parts = []
    for _ in range(2):
        assert der[i] == 0x02
        n = der[i + 1]
        parts.append(der[i + 2:i + 2 + n].lstrip(b"\x00").rjust(32, b"\x00"))
        i += 2 + n
    return parts[0] + parts[1]


def _sign(data):
    """ES256 over the APNs key, in DER.

    Windows brings no openssl - there every push failed silently with
    FileNotFoundError (12.09.2026). So: sign with `cryptography` where it is
    installed, otherwise with openssl, which macOS ships.
    """
    key = os.path.expanduser(_cfg["key_path"])
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError:
        return subprocess.run(["openssl", "dgst", "-sha256", "-sign", key],
                              input=data, capture_output=True, check=True, timeout=10).stdout
    with open(key, "rb") as fh:
        schluessel = serialization.load_pem_private_key(fh.read(), password=None)
    return schluessel.sign(data, ec.ECDSA(hashes.SHA256()))


def _token(fresh=False):
    """The provider token, reused for 40 minutes - Apple refuses a new one
    per request, and rejects one older than an hour."""
    global _jwt
    with _lock:
        tok, at = _jwt
        if tok and not fresh and time.time() - at < 40 * 60:
            return tok
        head = _b64(json.dumps({"alg": "ES256", "kid": _cfg["key_id"]}, separators=(",", ":")).encode())
        claims = _b64(json.dumps({"iss": _cfg["team_id"], "iat": int(time.time())},
                                 separators=(",", ":")).encode())
        der = _sign(f"{head}.{claims}".encode())
        tok = f"{head}.{claims}.{_b64(_der_to_raw(der))}"
        _jwt = (tok, time.time())
        return tok


# ---------- sending ----------

def _post(device, payload, push_type, priority, collapse, fresh=False):
    """One notification to one phone; returns Apple's status and reason.

    Apple speaks only HTTP/2. macOS brings a curl that can; the curl Windows
    ships cannot ("the installed libcurl version does not support this"), and
    every push failed there in silence (12.09.2026). So: httpx where it has
    HTTP/2, curl otherwise.
    """
    kopf = {"authorization": f"bearer {_token(fresh)}",
            "apns-topic": _cfg["topic"],
            "apns-push-type": push_type,
            "apns-priority": str(priority)}
    if collapse:
        kopf["apns-collapse-id"] = collapse[:64]
    ziel = f"https://{HOSTS[device['env']]}/3/device/{device['token']}"

    try:
        import httpx                                  # noqa: PLC0415 - optional
        import h2                                     # noqa: F401, PLC0415
    except ImportError:
        return _post_curl(kopf, ziel, payload)
    try:
        with httpx.Client(http2=True, timeout=15) as c:
            r = c.post(ziel, headers=kopf, content=json.dumps(payload).encode())
        grund = ""
        if r.content:
            try:
                grund = r.json().get("reason", "")
            except ValueError:
                grund = r.text[:80]
        return r.status_code, grund
    except Exception as f:                            # noqa: BLE001 - report, never raise
        return 0, f"{type(f).__name__}: {f}"[:120]


def _post_curl(kopf, ziel, payload):
    """The way over curl - macOS ships one that speaks HTTP/2."""
    # The bearer token goes in a file, not on the command line, so it never
    # shows up in `ps`.
    fd, path = tempfile.mkstemp(prefix="iris-apns-")
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(f"{k}: {v}" for k, v in kopf.items()))
    try:
        r = subprocess.run(["curl", "--http2", "-s", "--max-time", "15", "-H", "@" + path,
                            "-o", "-", "-w", "\n%{http_code}", "--data-binary", "@-", ziel],
                           input=json.dumps(payload).encode(), capture_output=True, timeout=25)
    except (OSError, subprocess.SubprocessError) as f:
        return 0, f"{type(f).__name__}: {f}"[:120]
    finally:
        os.unlink(path)
    body, _, code = r.stdout.decode(errors="replace").rpartition("\n")
    try:
        code = int(code)
    except ValueError:
        code = 0
    grund = ""
    if body.strip():
        try:
            grund = json.loads(body).get("reason", "")
        except ValueError:
            grund = body.strip()[:80]
    return code, grund


def deliver(payload, push_type="alert", priority=10, collapse=None):
    """Send to every registered phone and say what came back."""
    global last_results
    results = []
    for d in devices():
        code, reason = _post(d, payload, push_type, priority, collapse)
        if code == 403 and reason in ("ExpiredProviderToken", "InvalidProviderToken"):
            code, reason = _post(d, payload, push_type, priority, collapse, fresh=True)
        if code == 400 and reason == "BadDeviceToken":
            # A debug build talks to the sandbox, a release build to
            # production; a token from one is refused by the other.
            other = "production" if d["env"] == "sandbox" else "sandbox"
            code2, reason2 = _post({**d, "env": other}, payload, push_type, priority, collapse)
            if code2 == 200:
                _update(d["token"], env=other)
                code, reason = code2, reason2
        if code == 410 or reason == "Unregistered":
            _forget(d["token"])                # the app is gone from that phone
        elif code == 200:
            _update(d["token"], last_ok=time.time())
        results.append({"device": d.get("name") or d["token"][:8], "env": d["env"],
                        "status": code, "reason": reason})
    last_results = results
    return results


def send(payload, push_type="alert", priority=10, collapse=None):
    """Send in the background; the bridge never waits on Apple."""
    if not configured() or not devices():
        return False
    threading.Thread(target=deliver, args=(payload, push_type, priority, collapse),
                     daemon=True).start()
    return True


# ---------- what gets pushed ----------

def ask(title, key, card, watched):
    """An approval or a question is waiting."""
    if watched and not _away():
        return False
    tool = card.get("tool") or "?"
    rid = card.get("request_id")
    iris = {"kind": "ask", "key": key, "request_id": rid, "tool": tool,
            "machine": config.machine_name()}
    if tool == "AskUserQuestion":
        qs = (card.get("input") or {}).get("questions") or []
        q = qs[0] if qs else {}
        iris["question"] = q.get("question", "")
        alert = {"title": title, "subtitle": q.get("question") or "Frage",
                 "body": " · ".join(o.get("label", "") for o in q.get("options") or [])
                 or "Antwort nötig"}
        category = "FRAGE"
    else:
        body = card.get("detail") or ""
        ch = card.get("change") or {}
        if tool == "Write" and ch:
            body += f" · {ch.get('added', 0)} Zeilen"
        elif tool in ("Edit", "MultiEdit") and ch:
            body += f" · +{ch.get('added', 0)} −{ch.get('removed', 0)}"
        alert = {"title": title, "subtitle": TITLES.get(tool, tool), "body": body[:240]}
        category = "FREIGABE"
    ok = send({"aps": {"alert": alert, "sound": "default", "category": category,
                       "thread-id": key, "interruption-level": "time-sensitive"},
               "iris": iris}, collapse=rid)
    if ok and rid:
        _pushed.add(rid)
    return ok


def settled(request_id):
    """Answered - at the Mac, in the app, or timed out. The phone takes the
    notification down, so nobody later taps Allow on something long gone."""
    if request_id not in _pushed:
        return False
    _pushed.discard(request_id)
    return send({"aps": {"content-available": 1},
                 "iris": {"kind": "settled", "request_id": request_id}},
                push_type="background", priority=5)


# Am Ende eines Zuges: steht dort eine Frage an dich?
#
# Im Auto-Modus braucht eine Sitzung keine Freigabe. Sie arbeitet ihre Aufgabe
# ab und endet mit einer Frage - und genau davon erfuhr niemand: fuer die
# Bruecke war das ein normal beendeter Zug, also hoechstens "Fertig" nach 90
# Sekunden. Calvin am 25.09.: "die realsense-Sitzung hat grad ne Frage an
# mich, die krieg ich aber nicht mit, nur wenn ich da raufgehe und gucke."
# Ein kurzer Nachsatz in Klammern darf hinter dem Fragezeichen stehen
# ("Passt das so? (kurz bestaetigen)") - ein langer nicht, sonst faengt die
# Regel jeden Absatz ein, in dem irgendwo ein Fragezeichen vorkam.
_SCHLUSS = r'''[\s\*_`\)\]"'»“”]*'''
_FRAGE_ENDE = re.compile(r'''\?''' + _SCHLUSS + r'''(\([^()]{0,60}\))?''' + _SCHLUSS + r'''$''')


def _endet_mit_frage(text):
    """Ob der letzte Absatz eine Frage an den Nutzer ist.

    Bewusst schlicht: das Fragezeichen am Ende. Eine Erkennung nach Wortlaut
    ("soll ich", "welche") trifft mehr Faelle und mehr Fehlalarme, und ein
    Fehlalarm ist hier teuer - er meldet sich am Telefon.
    """
    zeilen = [z.strip() for z in (text or "").strip().splitlines() if z.strip()]
    if not zeilen:
        return False
    letzte = zeilen[-1]
    if letzte.startswith("```") or letzte.startswith("|"):
        return False           # Codeblock oder Tabelle, keine Ansprache
    return bool(_FRAGE_ENDE.search(letzte))


# Fuer die Mitteilung: eine Zeile, die auch den Zusammenhang nennt.
#
# Die letzte Zeile allein ist oft "Welchen Weg willst du?" - eine Frage ohne
# das, worauf sie sich bezieht. In einer Mitteilung kann man nicht
# nachscrollen, also muss der Zusammenhang hinein. Ein kleines Modell fasst
# ihn zusammen; geht das schief oder dauert es zu lange, steht dort die letzte
# Zeile, wie vorher.
_KURZ_MODELL = "claude-haiku-4-5-20251001"
_KURZ_AUFTRAG = (
    "Fasse fuer eine Handy-Mitteilung zusammen, in HOECHSTENS 180 Zeichen, "
    "als EINE Zeile ohne Anrede und ohne Markdown: was gerade fertig wurde "
    "und was gefragt ist. Antworte nicht auf die Frage, gib nur die "
    "Zusammenfassung aus.\n\n"
)


def _schlicht(text):
    """Text, wie er in eine Mitteilung gehoert: ohne Markdown.

    Eine Mitteilung zeichnet nichts - `**fett**` steht dort als Sternchen da,
    und eine Tabellenzeile als Strichsalat. Calvin hat am 25.09. genau das auf
    dem Sperrbildschirm gesehen: „**Wo er auf dem Weg zu Jarvis steht:**" und
    darunter „| | Stand |".
    """
    zeilen = []
    for z in (text or "").splitlines():
        z = z.strip()
        # Tabellen, Codezaeune und Trennlinien tragen ohne Satz nichts.
        if not z or z.startswith("|") or z.startswith("```") or set(z) <= set("-—=·*_ "):
            continue
        z = re.sub(r"^#{1,6}\s*", "", z)          # Ueberschrift
        z = re.sub(r"^[-*+]\s+", "", z)           # Aufzaehlung
        z = re.sub(r"\*\*|__|`|\*", "", z)        # Auszeichnung
        zeilen.append(z)
    return " ".join(" ".join(zeilen).split())


def _kurzfassung(text, frist=25):
    from .session import CLAUDE_BIN
    text = _schlicht(text)
    if len(text) < 200:
        return text                    # kurz genug, da fehlt nichts
    try:
        # Ohne Hooks. Sonst haengt sich iris an den eigenen Aufruf: die
        # Kurzfassung wird zu einer sichtbaren Sitzung, bekommt als Titel den
        # Auftrag ("Fasse fuer eine Handy-Mitteilung zusammen …") und meldet
        # sich am Ende selbst auf dem Sperrbildschirm. Genau das stand am
        # 25.09. bei Calvin als Mitteilung. Der Hook haelt sich raus, sobald
        # IRIS_SESSION_KEY gesetzt ist - er nimmt es als "das fuehrt die
        # Bruecke selbst".
        umgebung = dict(os.environ, IRIS_SESSION_KEY="kurzfassung")
        r = subprocess.run([CLAUDE_BIN, "-p", "--model", _KURZ_MODELL],
                           input=_KURZ_AUFTRAG + text[:4000],
                           capture_output=True, text=True, timeout=frist,
                           env=umgebung)
        zeile = " ".join((r.stdout or "").split())
        if r.returncode == 0 and 10 < len(zeile) <= 400:
            return zeile
    except (OSError, subprocess.SubprocessError):
        pass
    return text


def wartet(title, key, text, watched):
    """Ein Zug ist zu Ende und endet mit einer Frage.

    Anders als `done` ohne Mindestdauer: eine Frage nach zehn Sekunden ist
    genauso unbeantwortet wie eine nach zehn Minuten. Und mit Antwortfeld -
    die Kategorie FRAGE traegt es, und ohne request_id schickt die App den
    Text als Nachricht in die Sitzung.
    """
    if watched and not _away():
        return False

    def los():
        zeilen = [z for z in _schlicht(text).split(". ") if z]
        frage = zeilen[-1] if zeilen else "Frage"
        koerper = _kurzfassung(text) or frage
        send({"aps": {"alert": {"title": title, "subtitle": "Wartet auf dich",
                                "body": koerper[:240]},
                      "category": "FRAGE", "thread-id": key,
                      "interruption-level": "time-sensitive"},
              "iris": {"kind": "wartet", "key": key,
                       "machine": config.machine_name()}})

    # In einem eigenen Faden: die Zusammenfassung dauert Sekunden, und der
    # Lesefaden der Sitzung darf darauf nicht warten.
    threading.Thread(target=los, daemon=True).start()
    return True


def assistent(titel, key, text):
    """Der Assistent hat etwas gesagt.

    Ohne Mindestdauer und ohne Ruecksicht darauf, ob jemand hinsieht: wenn
    **er** etwas sagt, ist das eine Nachricht an Calvin, keine Fertigmeldung
    einer Arbeitssitzung. Die 90-Sekunden-Regel ist fuer Sitzungen gemacht, in
    denen gearbeitet wird - hier waere sie schlicht falsch, und seine erste
    Antwort kam deshalb gar nicht an (25.09.).
    """
    koerper = _schlicht(text)
    if not koerper:
        return False
    if len(koerper) > 200:
        koerper = _kurzfassung(text) or koerper
    return send({"aps": {"alert": {"title": titel or "Assistent",
                                   "body": koerper[:240]},
                         "category": "FRAGE", "thread-id": key,
                         "interruption-level": "time-sensitive"},
                 "iris": {"kind": "assistent", "key": key,
                          "machine": config.machine_name()}})


def done(title, key, seconds, acts, watched, text=""):
    """Ein langer Zug ist zu Ende.

    Frueher stand dort nur "nach 3:21 · 12 Befehle" - das sagt, DASS etwas
    passiert ist, nicht WAS. Calvin am 25.09.: "traegt nichts, die Antwort",
    und zur Dauer samt Befehlszahl: "uninteressant". Also steht dort die
    Antwort, und sonst nichts. Die Zahlen stehen in der Sitzung, wer sie
    braucht, findet sie dort.
    """
    if seconds < DONE_AFTER or (watched and not _away()):
        return False

    def los():
        schlicht = _schlicht(text)
        koerper = _kurzfassung(text) if schlicht else ""
        if not koerper:
            koerper = schlicht
        if not koerper:
            # Nichts gesagt, nur gearbeitet - dann bleibt die Dauer als
            # einziges, was ueberhaupt etwas mitteilt.
            s = int(seconds)
            koerper = f"nach {s // 60}:{s % 60:02d}"
        send({"aps": {"alert": {"title": title, "subtitle": "Fertig",
                                "body": koerper[:240]},
                      "sound": "default", "category": "FERTIG", "thread-id": key},
              "iris": {"kind": "done", "key": key, "machine": config.machine_name()}})

    # Wie bei `wartet`: die Kurzfassung dauert Sekunden, die Sitzung wartet
    # nicht darauf.
    threading.Thread(target=los, daemon=True).start()
    return True


def status():
    return {"configured": configured(), "topic": _cfg.get("topic"),
            "devices": [{"name": d.get("name"), "env": d["env"], "added": d.get("added"),
                         "last_ok": d.get("last_ok")} for d in devices()],
            "last": last_results}
