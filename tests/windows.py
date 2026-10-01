"""End to end on the Windows PC: a claude session in a console there, driven
through that PC's bridge the way the phone does it.

  IRIS_PC_TOKEN=... python3 tests/windows.py [http://<pc>:8780]

Rechner und Adresse aus rechner.env (IRIS_PC, IRIS_PC_URL).

Opens its own console on the PC (a scheduled task in the logged-in session,
so it can be typed into), types a message, answers a question with options,
sends lines as one message, opens /status and closes it with Esc, then ends
the session. Only neutral words go in.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

try:
    from tests.rechner import brauche
except ImportError:                     # als Skript gestartet: tests/ liegt vorn
    from rechner import brauche

HOST = brauche("IRIS_PC", "der SSH-Name des Windows-PCs")
BASE = sys.argv[1] if len(sys.argv) > 1 else brauche(
    "IRIS_PC_URL", "die Adresse seiner Bruecke")
TOKEN = os.environ.get("IRIS_PC_TOKEN", "")


def _heim():
    """Der Heimatordner auf dem PC, dort erfragt statt hier eingetragen.
    Die Standardshell des Windows-OpenSSH ist PowerShell."""
    r = subprocess.run(["ssh", HOST, "echo $env:USERPROFILE"],
                       capture_output=True, text=True, timeout=30)
    heim = r.stdout.strip()
    if not heim:
        sys.exit(f"Heimatordner auf {HOST} nicht lesbar: {r.stderr.strip()[:200]}")
    return heim


HEIM = _heim()
CWD = HEIM + r"\iris-probe\wintest"
TITLE = "iris-test"
ok_count, fail = 0, []

LAUNCH = r"""@echo off
title iris-test
if not exist "%USERPROFILE%\iris-probe\wintest" mkdir "%USERPROFILE%\iris-probe\wintest"
cd /d "%USERPROFILE%\iris-probe\wintest"
claude --model opus --no-chrome
"""
TASK = r"""$user = (Get-CimInstance Win32_ComputerSystem).UserName
schtasks /create /tn 'iris Test' /tr "$env:USERPROFILE\iris-probe\wintest.cmd" /sc once /st 23:59 /ru $user /it /f | Out-Null
schtasks /run /tn 'iris Test' | Out-Null
Start-Sleep -Seconds 3
schtasks /delete /tn 'iris Test' /f | Out-Null
"""


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
        print(f"  ok   {name}")
    else:
        fail.append(name)
        print(f"  FAIL {name} {detail}")


def req(path, body=None, timeout=20):
    r = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN},
        method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return f.status, json.loads(f.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def backlog(key, seconds=1.5):
    r = urllib.request.Request(f"{BASE}/api/sessions/{key}/events?since=0",
                               headers={"Authorization": "Bearer " + TOKEN})
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


def until(fn, timeout, step=1.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return None


def ssh(cmd, stdin=None):
    # PowerShell answers in the console's code page, not UTF-8.
    return subprocess.run(["ssh", HOST, cmd], input=stdin, capture_output=True,
                          text=True, errors="replace", timeout=60)


def ours():
    _, d = req("/api/sessions")
    for s in d.get("sessions", []):
        if s.get("terminal") and not s.get("exited") \
                and (s.get("cwd") or "").rstrip("\\").lower() == CWD.lower():
            return s
    return None


def screen(key):
    _, d = req(f"/api/sessions/{key}/screen")
    return d.get("text") or d.get("screen") or ""


def said(key, word):
    return any(c.get("kind") == "say" and word.lower() in (c.get("text") or "").lower()
               for c in backlog(key))


def idle(key):
    _, d = req(f"/api/sessions/{key}")
    s = d.get("session") or {}
    return not s.get("busy")


def launch():
    """Copy the launcher over and start it as a task in the logged-in
    session - from ssh itself no console could be typed into."""
    print("Konsole mit claude öffnen")
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        for name, text in (("wintest.cmd", LAUNCH.replace("\n", "\r\n")), ("wintest-task.ps1", TASK)):
            with open(os.path.join(d, name), "w", encoding="ascii", newline="") as fh:
                fh.write(text)
        subprocess.run(["scp", "-q", os.path.join(d, "wintest.cmd"), os.path.join(d, "wintest-task.ps1"),
                        f"{HOST}:iris-probe/"], check=True, timeout=60)
    ssh("powershell -NoProfile -ExecutionPolicy Bypass -File " + HEIM + r"\iris-probe\wintest-task.ps1")


def main():
    if not TOKEN:
        sys.exit("IRIS_PC_TOKEN fehlt")
    _, a = req("/api/terminals/away")
    print("unterwegs:", a.get("away"))
    if ours():
        # The folder is the test's own: a session there is one of ours.
        print("Konsole aus einem früheren Lauf ist noch offen")
    else:
        launch()
    s = until(lambda: (lambda x: x if x and x.get("typable") else None)(ours()), 90, 2)
    check("Sitzung gefunden und tippbar", s is not None)
    if not s:
        return
    key = s["key"]
    until(lambda: idle(key), 30)

    print("Nachricht eintippen")
    code, r = req(f"/api/sessions/{key}/message",
                  {"text": "Antworte nur mit dem Wort Basalt."})
    check("angenommen und eingetippt", code == 200 and r.get("typed"), f"{code} {r}")
    check("Claude antwortet", until(lambda: said(key, "Basalt"), 120, 2) is not None)
    until(lambda: idle(key), 60)

    print("Frage mit Auswahl")
    req(f"/api/sessions/{key}/message",
        {"text": "Stell mir mit dem Werkzeug AskUserQuestion genau eine Frage: "
                 "Wolfram oder Zinn? Genau diese zwei Optionen. Danach antworte "
                 "nur mit dem gewählten Wort."})

    def open_ask():
        cards = backlog(key)
        done = {c.get("request_id") for c in cards if c.get("kind") == "answered"}
        for c in cards:
            if c.get("kind") == "ask" and c.get("tool") == "AskUserQuestion" \
                    and c.get("request_id") not in done:
                return c
        return None
    ask = until(open_ask, 120, 2)
    check("Frage kommt an", ask is not None)
    if ask:
        q = ((ask.get("input") or {}).get("questions") or [{}])[0]
        until(lambda: "Enter to select" in screen(key), 20)
        code, r = req(f"/api/sessions/{key}/permission",
                      {"request_id": ask["request_id"], "allow": True,
                       "answers": {q.get("question", ""): "Wolfram"}})
        check("Antwort angenommen", code == 200 and r.get("ok"), f"{code} {r}")
        check("Claude nimmt Wolfram", until(lambda: said(key, "Wolfram"), 120, 2) is not None)
    until(lambda: idle(key), 60)

    print("Mehrere Zeilen als eine Nachricht")
    code, r = req(f"/api/sessions/{key}/message",
                  {"text": "Erste Zeile Kobalt\nZweite Zeile Nickel\nAntworte nur mit: angekommen"})
    check("Zeilen eingetippt", code == 200 and r.get("typed"), f"{code} {r}")
    # Typed text is not announced again as "sent" (the phone shows it
    # already); a Return between the lines would have sent the first alone,
    # and Claude would not answer with the word of the last one.
    check("als eine Nachricht beantwortet", until(lambda: said(key, "angekommen"), 120, 2) is not None)
    check("kein Fehler beim Eintippen", not any(c.get("kind") == "error" for c in backlog(key)))
    until(lambda: idle(key), 60)

    print("Lange Nachricht, 1500 Zeichen")
    # Claude Code on Windows once dropped the beginning of long input.
    filler = " ".join(["Granit"] * 200)
    long_text = ("Anfang Obsidian. " + filler + " Ende. Antworte nur mit dem ersten Wort "
                 "dieser Nachricht nach dem Wort Anfang.")
    code, r = req(f"/api/sessions/{key}/message", {"text": long_text})
    check("lange Nachricht eingetippt", code == 200 and r.get("typed"), f"{code} {r}")
    check("Anfang kam an", until(lambda: said(key, "Obsidian"), 120, 2) is not None)
    until(lambda: idle(key), 60)

    print("Ansicht öffnen und mit Esc schließen")
    req(f"/api/sessions/{key}/message", {"text": "/status"})
    check("/status offen", until(lambda: "esc to" in screen(key).lower(), 20) is not None)
    code, r = req(f"/api/sessions/{key}/keys", {"key": "esc"})
    check("Esc angenommen", code == 200, f"{code} {r}")
    check("/status zu", until(lambda: "esc to" not in screen(key).lower(), 15) is not None)

    print("Aufräumen")
    req(f"/api/sessions/{key}/message", {"text": "/exit"})
    gone = until(lambda: ours() is None, 30, 2)
    if not gone:
        ssh('taskkill /FI "WINDOWTITLE eq iris-test*" /T /F')
    check("Sitzung beendet", gone is not None)


if __name__ == "__main__":
    try:
        main()
    finally:
        print(f"\n{ok_count} ok, {len(fail)} fehlgeschlagen" + (f": {', '.join(fail)}" if fail else ""))
