"""End-to-end test of the way into a terminal session: a real interactive
claude in a real Terminal.app window, a real bridge on a side port.

It proves what the phone depends on: a message reaches a session that
finished its turn, one that is still working, and one that never sent a
single hook - typed into its tab, standing there as a normal prompt, and
shown on the phone exactly once. And a running turn can be stopped.

It opens Terminal windows for the duration and closes them afterwards. The
sessions run in a scratch folder under ~/Library/Caches/iris-test (home is
trusted, so no trust dialog comes up). Runs on the default model, so it
costs a little quota.
"""
import glob
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

PORT = 8775
BASE = f"http://127.0.0.1:{PORT}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAUDE = shutil.which("claude") or "/opt/homebrew/bin/claude"
sys.path.insert(0, ROOT)
from bridge import config, terminals, typist  # noqa: E402

ok_count = 0
fail = []
WINDOWS = []


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
        print(f"  ok   {name}")
    else:
        fail.append(name)
        print(f"  FAIL {name} {detail}")


def req(path, token, body=None, timeout=20):
    r = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return f.status, json.loads(f.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def backlog(key, token, seconds=1.5):
    r = urllib.request.Request(f"{BASE}/api/sessions/{key}/events?since=0",
                               headers={"Authorization": "Bearer " + token})
    got, start = [], time.time()
    try:
        with urllib.request.urlopen(r, timeout=8) as fh:
            for line in fh:
                if line.startswith(b"data: "):
                    got.append(json.loads(line[6:].decode()))
                if time.time() - start > seconds:
                    break
    except (TimeoutError, OSError):
        pass
    return got


def until(fn, timeout, step=0.5):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def osascript(script):
    return subprocess.run(["osascript", "-e", script], capture_output=True,
                          text=True, timeout=20).stdout.strip()


def open_window(cwd, hook_port):
    """A Terminal window running claude in `cwd`: (window id, tty)."""
    cmd = f"cd {shlex.quote(cwd)} && IRIS_HOOK_PORT={hook_port} {shlex.quote(CLAUDE)}"
    out = osascript('tell application "Terminal"\n'
                    f'set t to do script "{cmd}"\n'
                    'delay 1\n'
                    'return (id of window 1 as text) & " " & (tty of t)\n'
                    'end tell')
    wid, tty = out.split(" ", 1)
    WINDOWS.append(wid)
    return wid, tty


def screen(wid):
    return osascript(f'tell application "Terminal" to get history of '
                     f'(first tab of window id {wid})')


def session_in(cwd, token):
    real = os.path.realpath(cwd)
    _, d = req("/api/sessions", token)
    for s in d.get("sessions", []):
        if s.get("terminal") and os.path.realpath(s.get("cwd") or "") == real:
            return s
    return None


def said(key, token, word):
    return any(c["kind"] == "say" and word.lower() in (c.get("text") or "").lower()
               for c in backlog(key, token))


def last_prompt(sid):
    """The last thing sent to Claude as input, from the transcript."""
    from bridge import history
    path = history.find_transcript(sid)
    last = None
    for line in open(path) if path else []:
        d = json.loads(line)
        if d.get("type") != "user" or d.get("isMeta"):
            continue
        c = d.get("message", {}).get("content")
        text = c if isinstance(c, str) else " | ".join(
            x.get("text") or "" for x in c or [] if isinstance(x, dict) and x.get("type") == "text")
        if text and not text.startswith("["):
            last = text.strip()
    return last


def ready(sid):
    """Claude is up and at its prompt."""
    return typist.status(sid) == "idle"

try:
    from tests.port import muss_frei_sein, muss_leben
except ImportError:                     # als Skript gestartet
    from port import muss_frei_sein, muss_leben


def main():
    token = config.load()["token"]
    scratch = os.path.join(os.path.expanduser("~/Library/Caches/iris-test"),
                           uuid.uuid4().hex[:8])
    wd_a, wd_b = os.path.join(scratch, "a"), os.path.join(scratch, "b")
    os.makedirs(wd_a)
    os.makedirs(wd_b)
    with open(os.path.join(wd_a, "notiz.txt"), "w") as fh:
        fh.write("Die Brücke steht.\n")
    state = tempfile.mkdtemp(prefix="iris-typing-")
    benv = dict(os.environ, IRIS_NO_PUSH="1", IRIS_DISCOVER_TESTS="1",
                IRIS_AWAY_PATH=os.path.join(state, "away.json"),
                IRIS_TERMINALS_PATH=os.path.join(state, "terminals.json"))
    benv.pop("IRIS_SESSION_KEY", None)
    # What the test bridge says - when it dies, this is where the reason is.
    bridge_log = os.path.join(state, "bridge.log")

    def start_bridge():
        log = open(bridge_log, "a")
        return subprocess.Popen(
            [sys.executable, "-m", "bridge", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=ROOT, env=benv, stdout=log, stderr=subprocess.STDOUT)

    muss_frei_sein(PORT)
    bridge = start_bridge()
    try:
        until(lambda: req("/api/health", token, timeout=1)[0] == 200
              if _up() else None, 10)

        print("Sitzung, die fertig ist")
        wid_a, tty_a = open_window(wd_a, PORT)
        s = until(lambda: session_in(wd_a, token), 60)
        check("Sitzung erscheint", bool(s))
        if not s:
            return
        key, sid = s["key"], s["claude_session_id"]
        check("Tab zum Eintippen gefunden",
              until(lambda: (session_in(wd_a, token) or {}).get("typable"), 15))
        until(lambda: ready(sid), 30)
        time.sleep(1.5)
        print("Modus")
        # Before the first turn: afterwards Claude often leaves a grey
        # suggestion in the input, and then the bridge rightly refuses.
        code, r = req(f"/api/sessions/{key}/mode", token, {"mode": "plan"})
        check("Auf Plan umgestellt", code == 200 and r.get("mode") == "plan", f"({code} {r})")
        check("Statuszeile zeigt Plan",
              typist.mode_on_screen(typist.screen_now(tty_a)) == "plan")
        code, r = req(f"/api/sessions/{key}/mode", token, {"mode": "auto"})
        check("Zurück auf Auto", code == 200 and r.get("mode") == "auto", f"({code} {r})")

        code, r = req(f"/api/sessions/{key}/message", token,
                      {"text": "Sag nur das Wort: Messing"})
        check("Sofort eingetippt", code == 200 and r.get("typed"), f"({code} {r})")
        check("Claude antwortet", until(lambda: said(key, token, "Messing"), 90))
        cards = backlog(key, token)
        check("Als eingetippt gemeldet",
              any(c["kind"] == "delivered" and c.get("via") == "terminal" for c in cards))
        check("Nachricht nur einmal in der App",
              not any(c["kind"] == "sent" and "Messing" in (c.get("text") or "")
                      for c in cards), f"({[c['kind'] for c in cards]})")
        check("Im Terminal zu sehen", "Sag nur das Wort: Messing" in screen(wid_a))

        print("Text zwischen Werkzeugaufrufen")
        typist.type_into(tty_a, "Schreibe zuerst genau den Satz: Ich lese jetzt die Notiz. "
                                "Lies dann notiz.txt. Schreibe danach genau: Gelesen, alles da.")
        check("Beide Sätze kommen an",
              until(lambda: said(key, token, "alles da"), 90)
              and said(key, token, "Ich lese jetzt die Notiz"))
        cards = backlog(key, token)
        first = next((i for i, c in enumerate(cards) if c["kind"] == "say"
                      and "Ich lese jetzt" in (c.get("text") or "")), None)
        # Nicht auf "Read" festnageln: womit Claude eine kleine Textdatei liest,
        # ist seine Entscheidung - Read hier, cat ueber Bash dort. Geprueft wird
        # die Eigenschaft, um die es geht (der Satz kommt VOR dem Werkzeugaufruf
        # an), nicht die Werkzeugwahl. Sonst meldet der Test einen Bruecken-
        # Fehler, wo keiner ist: am 12.09. zweimal "(13 / None)" gegen eine
        # Bruecke, die in echten Sitzungen Bash, Read, Write und Edit sauber
        # als Karten liefert. Welches Werkzeug es war, steht jetzt im Detail.
        read = next((i for i, c in enumerate(cards) if c["kind"] == "act"), None)
        werkzeuge = [c.get("tool") for c in cards if c["kind"] == "act"]
        check("Satz steht vor dem Werkzeugaufruf",
              first is not None and read is not None and first < read,
              f"({first} / {read}, Werkzeuge: {werkzeuge[:5]})")
        says = [(c["seq"], c.get("text") or "") for c in cards if c["kind"] == "say"]
        check("Kein Satz doppelt",
              sum(1 for _, t in says if "Ich lese jetzt" in t) == 1, f"({says[-6:]})")

        print("Neustart der Brücke")
        before = backlog(key, token)
        top = max(c["seq"] for c in before)
        bridge.terminate()
        bridge.wait(10)
        bridge = start_bridge()
        until(_up, 10)
        after = until(lambda: backlog(key, token) if session_in(wd_a, token) else None, 20) or []
        check("Verlauf nach dem Neustart vollständig",
              said(key, token, "Messing") and said(key, token, "alles da"),
              f"({len(after)} Karten)")
        check("Nummern laufen weiter", after and max(c["seq"] for c in after) >= top,
              f"({top} → {max((c['seq'] for c in after), default=0)})")

        print("Nachricht mit Foto")
        # A pasted image path becomes an attachment in Claude Code and the
        # Return after it gets lost - the bridge must notice and send it.
        photo = os.path.join(wd_a, "probe.png")
        subprocess.run(["sips", "-s", "format", "png", "/System/Library/CoreServices/"
                        "CoreTypes.bundle/Contents/Resources/GenericDocumentIcon.icns",
                        "--out", photo], capture_output=True)
        up = urllib.request.Request(f"{BASE}/api/sessions/{key}/upload", data=open(photo, "rb").read(),
                                    headers={"Authorization": "Bearer " + token,
                                             "X-Filename": "probe.png"}, method="POST")
        with urllib.request.urlopen(up, timeout=20) as f:
            path = json.loads(f.read()).get("path")
        until(lambda: ready(sid), 20)
        code, r = req(f"/api/sessions/{key}/message", token,
                      {"text": "Was ist auf dem Bild? Antworte mit einem Satz, der mit Bild: beginnt.",
                       "attachments": [path], "id": "foto-1"})
        check("Foto angenommen", code == 200 and r.get("typed"), f"({code} {r})")
        check("Als abgeschickt bestätigt",
              until(lambda: any(c["kind"] == "delivered" for c in backlog(key, token)[-8:]), 20))
        # What Claude says about the picture varies in wording; what counts is
        # an answer after the photo went in that talks about a picture.
        def about_picture():
            cards = backlog(key, token)
            went = max((i for i, c in enumerate(cards) if c["kind"] == "delivered"), default=None)
            if went is None:
                return None
            for c in cards[went:]:
                t = (c.get("text") or "").lower() if c["kind"] == "say" else ""
                if any(w in t for w in ("bild", "dokument", "symbol", "icon")):
                    return t
            return None
        seen = until(about_picture, 120)
        says = [(c.get("text") or "")[:80] for c in backlog(key, token) if c["kind"] == "say"][-3:]
        check("Claude sieht das Bild", bool(seen), f"(letzte Antworten: {says})")
        code, r = req(f"/api/sessions/{key}/message", token,
                      {"text": "Was ist auf dem Bild? Antworte mit einem Satz, der mit Bild: beginnt.",
                       "attachments": [path], "id": "foto-1"})
        check("Wiederholung wird nicht nochmal geschickt", code == 200 and r.get("duplicate"),
              f"({code} {r})")

        print("Sitzung, die noch arbeitet")
        # Long enough to still be at work when the phone's message comes,
        # and nothing a permission classifier would stop.
        typist.type_into(tty_a, "Schreibe ein Gedicht mit acht Strophen über eine "
                                "Salbeipflanze. Die letzte Zeile ist nur das Wort: Salbei")
        check("Zug läuft", until(lambda: (session_in(wd_a, token) or {}).get("busy"), 30))
        time.sleep(1)
        # Typed at the Mac while Claude works: Claude Code keeps it as a queued
        # command, not as a user record - the phone must still show it.
        typist.type_into(tty_a, "Zwischendurch am Mac: sag am Ende auch das Wort Zinnober")
        # It shows at once, greyed as waiting, and turns into a turn of its
        # own once Claude takes it.
        check("Einschub vom Mac erscheint in der App",
              until(lambda: any(c["kind"] in ("sent", "pending") and "Zinnober" in (c.get("text") or "")
                                for c in backlog(key, token)), 60))
        code, r = req(f"/api/sessions/{key}/message", token,
                      {"text": "Sag nur das Wort: Kupfer"})
        # Typed at once, while Claude works - Claude Code takes it after the
        # step it is on, the way the Claude app slips messages in. Waiting for
        # the end of the turn left messages hanging for hours in a long one.
        check("Sofort eingetippt, auch mitten im Zug", code == 200 and r.get("typed"), f"({code} {r})")
        check("Als eingetippt bestätigt",
              until(lambda: any(c["kind"] == "delivered" for c in backlog(key, token)[-12:]), 20))
        check("Claude nimmt sie auf", until(lambda: said(key, token, "Kupfer"), 150))
        cards = backlog(key, token)
        check("Nachricht nur einmal",
              sum(1 for c in cards if c["kind"] in ("sent", "queued")
                  and "Kupfer" in (c.get("text") or "")) == 1)
        check("Einschub vom Mac nur einmal",
              sum(1 for c in cards if c["kind"] in ("sent", "pending")
                  and "Zinnober" in (c.get("text") or "")) == 1)
        check("Einschub vom Mac von Claude übernommen",
              any(c["kind"] in ("taken", "sent") and "Zinnober" in (c.get("text") or "") for c in cards))

        print("Ansicht eines Befehls")
        # /status opens a view in the terminal. The phone sees the screen
        # and closes it with Esc - sent as CSI 27 u, the only Esc that
        # survives the Return `do script` adds.
        check("Zug vorbei", until(lambda: not (session_in(wd_a, token) or {}).get("busy"), 180))
        time.sleep(2)
        code, r = req(f"/api/sessions/{key}/message", token, {"text": "/status"})
        check("Befehl eingetippt", code == 200 and r.get("typed"), f"({code} {r})")
        shown = lambda: (req(f"/api/sessions/{key}/screen", token)[1] or {})
        check("Ansicht auf dem Handy zu sehen",
              until(lambda: shown().get("view") and "Version" in shown().get("text", ""), 20))
        code, r = req(f"/api/sessions/{key}/keys", token, {"key": "esc"})
        check("Esc angenommen", code == 200 and r.get("ok"), f"({code} {r})")
        check("Esc schließt die Ansicht", until(lambda: not shown().get("view"), 15))
        check("Eingabe wieder frei", until(lambda: typist.input_empty(typist.screen_now(tty_a) or ""), 10))
        # Sent while a view is open, a message waits for it to close instead
        # of landing in it - and goes once Esc closed it.
        code, r = req(f"/api/sessions/{key}/message", token, {"text": "/status"})
        check("Ansicht wieder offen", until(lambda: shown().get("view"), 20))
        code, r = req(f"/api/sessions/{key}/message", token, {"text": "Sag nur das Wort: Wolfram"})
        check("Nachricht angenommen", code in (200, 202), f"({code} {r})")
        check("App erfährt von der offenen Ansicht",
              until(lambda: any(c["kind"] == "view" and c.get("open")
                                for c in backlog(key, token)[-20:]), 15))
        time.sleep(2)
        check("Nicht in die Ansicht getippt",
              shown().get("view") and "Wolfram" not in shown().get("text", ""))
        req(f"/api/sessions/{key}/keys", token, {"key": "esc"})
        check("Nach Esc abgeschickt", until(lambda: said(key, token, "Wolfram"), 120))

        print("Anhalten")
        typist.type_into(tty_a, "Schreibe eine Geschichte über eine Messingglocke mit "
                                "25 Absätzen. Das letzte Wort ist: Zuspät")
        check("Zug läuft", until(lambda: (session_in(wd_a, token) or {}).get("busy"), 30))
        time.sleep(4)
        code, r = req(f"/api/sessions/{key}/interrupt", token, {})
        check("Anhalten angenommen", code == 200 and r.get("ok"), f"({code} {r})")
        check("Zug angehalten",
              until(lambda: not (session_in(wd_a, token) or {"busy": 1}).get("busy"), 20))
        time.sleep(2)
        check("Nichts mehr ausgeführt", not said(key, token, "Zuspät"))
        code, r = req(f"/api/sessions/{key}/message", token,
                      {"text": "Sag nur das Wort: Bronze"})
        # Right after a stop the input is being cleaned, so it may wait a moment.
        check("Danach wieder angenommen", code in (200, 202) and r.get("ok"), f"({code} {r})")
        check("Claude antwortet", until(lambda: said(key, token, "Bronze"), 90))
        # Claude puts a stopped request back into the input at times; the
        # message must not be glued to it.
        check("Nachricht allein abgeschickt",
              last_prompt(sid) == "Sag nur das Wort: Bronze", f"({last_prompt(sid)!r})")

        def open_question():
            _, d = req(f"/api/sessions/{key}", token)
            asks = [c for c in backlog(key, token) if c["kind"] == "ask"
                    and c.get("tool") == "AskUserQuestion"]
            answered = {c.get("request_id") for c in backlog(key, token) if c["kind"] == "answered"}
            waiting = [c for c in asks if c["request_id"] not in answered]
            return waiting[-1] if waiting else None

        for away, color, pick in ((False, "Frage am Rechner", "Salbei"),
                                  (True, "Frage unterwegs", "Messing")):
            print(color)
            req("/api/terminals/away", token, {"away": away})
            until(lambda: ready(sid), 20)
            typist.type_into(tty_a, "Benutze jetzt das Werkzeug AskUserQuestion mit genau einer "
                                    "Frage: Welche Farbe? Optionen: Messing und Salbei. "
                                    "Antworte danach nur mit der gewählten Farbe.")
            q = until(open_question, 90)
            check("Frage kommt aufs Handy", bool(q))
            if not q:
                continue
            question = q["input"]["questions"][0]["question"]
            if not away:
                # At the Mac the dialog shows; the answer is typed into it.
                until(lambda: question in (typist.screen_now(tty_a) or ""), 20)
            code, r = req(f"/api/sessions/{key}/permission", token,
                          {"request_id": q["request_id"], "allow": True,
                           "answers": {question: pick}})
            check("Antwort angenommen", code == 200 and r.get("ok"), f"({code} {r})")
            check("Claude hat die Wahl", until(lambda: said(key, token, pick), 90))
            check("Frage auf dem Handy erledigt", until(lambda: not open_question(), 20))
        req("/api/terminals/away", token, {"away": False})

        print("Sitzung ohne einen einzigen Hook")
        wid_b, tty_b = open_window(wd_b, 9)       # hooks go nowhere
        sb = until(lambda: session_in(wd_b, token), 30)
        check("Erscheint trotzdem", bool(sb))
        if sb:
            until(lambda: ready(sb["claude_session_id"]), 30)
            time.sleep(1.5)
            code, r = req(f"/api/sessions/{sb['key']}/message", token,
                          {"text": "Sag nur das Wort: Zinn"})
            check("Sofort eingetippt", code == 200 and r.get("typed"), f"({code} {r})")
            check("Antwort kommt über das Transcript",
                  until(lambda: said(sb["key"], token, "Zinn"), 90))

        print("Fenster zu")
        typist.type_into(tty_a, "/exit")
        typist.type_into(tty_b, "/exit")
        check("Beendet gemeldet",
              until(lambda: (session_in(wd_a, token) or {}).get("exited"), 20))
        if sb:
            check("Ohne Hook: als beendet erkannt",
                  until(lambda: (session_in(wd_b, token) or {}).get("exited"), 20))
        code, r = req(f"/api/sessions/{key}/message", token, {"text": "noch da?"})
        check("Beendete Sitzung nimmt nichts an", code == 409, f"({code})")
    except Exception as e:                 # noqa: BLE001 - report, then clean up
        fail.append(f"abgebrochen: {e!r}")
        print(f"  FAIL abgebrochen: {e!r}")
    finally:
        if fail and os.path.exists(bridge_log):
            print("--- Ende des Protokolls der Testbrücke:")
            print("".join(open(bridge_log).readlines()[-40:]))
        for wid in WINDOWS:
            # End claude in the window first: closing one where it still
            # runs puts up "terminate running processes?" - a sheet that
            # blocks Terminal's scripting for every bridge until clicked.
            tty = osascript(f'tell application "Terminal" to get tty of tab 1 of window id {wid}')
            if tty.startswith("/dev/"):
                ps = subprocess.run(["ps", "-t", tty[5:], "-o", "pid=,command="],
                                    capture_output=True, text=True).stdout
                for line in ps.splitlines():
                    pid, _, cmd = line.strip().partition(" ")
                    if cmd.strip().endswith("claude") or "/claude " in cmd + " ":
                        subprocess.run(["kill", pid])
                time.sleep(2)
            try:
                osascript(f'tell application "Terminal" to close window id {wid}')
            except subprocess.TimeoutExpired:
                print(f"  Fenster {wid} ließ sich nicht schließen")
        bridge.terminate()
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.rmtree(state, ignore_errors=True)
        # The transcripts of the scratch sessions.
        for d in glob.glob(os.path.expanduser("~/.claude/projects/")
                           + scratch.replace("/", "-").replace(".", "-") + "*"):
            shutil.rmtree(d, ignore_errors=True)

    print(f"\n{ok_count} ok, {len(fail)} fehlgeschlagen")
    sys.exit(1 if fail else 0)


def _up():
    try:
        urllib.request.urlopen(BASE + "/api/health", timeout=1)
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False
    return True


if __name__ == "__main__":
    main()
