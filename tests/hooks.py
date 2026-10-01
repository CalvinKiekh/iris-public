"""End-to-end test of the terminal link: real `claude -p` runs, real hooks,
a real bridge on a side port.

A `claude -p` run stands in for a terminal session - to the hooks there is
no difference. The hook program is pointed at the test bridge through
IRIS_HOOK_PORT, and the away switch lives in a scratch file, so nothing
here touches the bridge you are actually using.

Runs on the default model, so it costs a little quota.
"""
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

PORT = 8777
BASE = f"http://127.0.0.1:{PORT}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, "hooks", "iris_hook.py")
CLAUDE = shutil.which("claude") or "/opt/homebrew/bin/claude"

ok_count = 0
fail = []


def check(name, cond, detail=""):
    global ok_count
    if cond:
        ok_count += 1
        print(f"  ok   {name}")
    else:
        fail.append(name)
        print(f"  FAIL {name} {detail}")


def req(path, token, body=None, timeout=20):
    headers = {"Content-Type": "application/json",
               "Authorization": "Bearer " + token}
    r = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode() if body is not None else None,
        headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return f.status, json.loads(f.read())


def backlog(key, token, seconds=2.0):
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


def terminals_in(wd, token):
    real = os.path.realpath(wd)
    _, d = req("/api/sessions", token)
    return [s for s in d["sessions"] if s.get("terminal")
            and os.path.realpath(s.get("cwd") or "") == real]


def wait_new(wd, token, seen, cond=lambda s: True, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        for s in terminals_in(wd, token):
            if s["claude_session_id"] not in seen and cond(s):
                return s
        time.sleep(0.2)
    return None


# Every claude run this test starts, so a phase that dies half-way does
# not leave one behind to talk to the next test's bridge.
SPAWNED = []


def claude(wd, prompt, env, mode="default"):
    p = subprocess.Popen(
        [CLAUDE, "-p", prompt, "--permission-mode", mode], cwd=wd, env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True)
    SPAWNED.append(p)
    return p

try:
    from tests.port import muss_frei_sein, muss_leben
except ImportError:                     # als Skript gestartet
    from port import muss_frei_sein, muss_leben


def main():
    sys.path.insert(0, ROOT)
    from bridge import config, install_hooks
    token = config.load()["token"]
    scratch = tempfile.mkdtemp(prefix="iris-hooks-")
    wd = os.path.join(scratch, "projekt")
    os.makedirs(wd)
    with open(os.path.join(wd, "hallo.txt"), "w") as fh:
        fh.write("Die Brücke steht.\n")

    benv = dict(os.environ, IRIS_AWAY_PATH=os.path.join(scratch, "away.json"), IRIS_NO_PUSH="1",
                IRIS_TERMINALS_PATH=os.path.join(scratch, "terminals.json"))
    benv.pop("IRIS_SESSION_KEY", None)

    def start_bridge():
        return subprocess.Popen(
            [sys.executable, "-m", "bridge", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=ROOT, env=benv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    muss_frei_sein(PORT)
    bridge = start_bridge()

    # The runs must look like a terminal, not like a session iris hosts.
    env = dict(os.environ, IRIS_HOOK_PORT=str(PORT))
    env.pop("IRIS_SESSION_KEY", None)

    # With the hooks installed globally they already fire here and follow
    # IRIS_HOOK_PORT; adding project hooks on top would count everything twice.
    if not install_hooks.installed_events():
        os.makedirs(os.path.join(wd, ".claude"))
        with open(os.path.join(wd, ".claude", "settings.json"), "w") as fh:
            json.dump(install_hooks.hook_settings(), fh)
        print("(Hooks nur für das Testprojekt eingetragen)")
    else:
        print("(Hooks sind global eingetragen)")

    try:
        for _ in range(40):
            try:
                req("/api/health", token, timeout=1)
                break
            except OSError:
                time.sleep(0.25)

        print("Hook-Programm")
        t0 = time.time()
        r = subprocess.run([sys.executable, "-S", HOOK],
                           input=json.dumps({"hook_event_name": "PreToolUse",
                                             "session_id": "x"}),
                           env=dict(env, IRIS_HOOK_PORT="9"),
                           capture_output=True, text=True, timeout=10)
        check("Ohne Brücke: sofort und wirkungslos durch",
              r.returncode == 0 and not r.stdout and time.time() - t0 < 1.5,
              f"(Code {r.returncode}, {time.time() - t0:.2f} s, {r.stdout!r})")

        subprocess.run([sys.executable, "-S", HOOK],
                       input=json.dumps({"hook_event_name": "SessionStart",
                                         "session_id": "eigene-sitzung",
                                         "cwd": wd}),
                       env=dict(env, IRIS_SESSION_KEY="abc"),
                       capture_output=True, text=True, timeout=10)
        _, d = req("/api/sessions", token)
        check("Eigene Sitzungen der Brücke werden ausgelassen",
              not any(s["claude_session_id"] == "eigene-sitzung"
                      for s in d["sessions"]))

        probe = json.dumps({"hook_event_name": "PostToolUse",
                            "session_id": "messung", "cwd": scratch,
                            "tool_name": "Read", "tool_use_id": "x",
                            "duration_ms": 1})
        times = []
        for _ in range(7):
            t0 = time.time()
            subprocess.run([sys.executable, "-S", HOOK], input=probe, env=env,
                           capture_output=True, text=True, timeout=10)
            times.append((time.time() - t0) * 1000)
        ms = statistics.median(times)
        print(f"       Aufschlag je Werkzeugaufruf: {ms:.0f} ms (Median aus 7)")
        check("Aufschlag bleibt unter 100 ms", ms < 100, f"({ms:.0f} ms)")

        print("Anmeldung und Mitlesen")
        seen = set()
        p = claude(wd, "Lies hallo.txt und gib nur ihren Inhalt zurück.", env,
                   mode="acceptEdits")
        out = p.communicate(timeout=180)[0]
        time.sleep(1.5)                      # let the tail catch up
        s = wait_new(wd, token, seen, timeout=10)
        check("Terminal-Sitzung gemeldet", bool(s))
        if s:
            seen.add(s["claude_session_id"])
            check("Sitzungs-ID bekannt", len(s["claude_session_id"]) > 20)
            check("Ende gemeldet", s["exited"], f"({s})")
            check("Befehle gezählt", s.get("acts", 0) >= 1, f"({s.get('acts')})")
            cards = backlog(s["key"], token)
            kinds = [c["kind"] for c in cards]
            check("Antwort mitgelesen",
                  any(c["kind"] == "say" and "Brücke" in c.get("text", "")
                      for c in cards), f"({kinds})")
            check("Werkzeugaufruf mitgelesen",
                  any(c["kind"] == "act" and c.get("tool") == "Read" for c in cards))
            check("Dauer aus dem Hook", "timing" in kinds, f"({kinds})")
            check("Zugende gemeldet", "done" in kinds)
            _, h = req(f"/api/sessions/{s['key']}/history", token)
            check("Keine doppelte Vorgeschichte", h["cards"] == [],
                  f"({len(h['cards'])} Karten)")
            # A claude -p run has no tab to type into: the mode cannot be
            # switched there (it can in a tab - tests/typing.py), and the
            # model never, since /model would change every new session too.
            # The reason names typing, not Terminal.app: since cea0f1c the
            # same rejection covers Windows consoles, which have no such app.
            try:
                req(f"/api/sessions/{s['key']}/mode", token, {"mode": "plan"})
                check("Modus ohne erreichbaren Tab abgewiesen", False, "(angenommen)")
            except urllib.error.HTTPError as e:
                body = json.loads(e.read() or b"{}")
                check("Modus ohne erreichbaren Tab abgewiesen",
                      e.code == 400 and "tippen" in (body.get("error") or ""),
                      f"(HTTP {e.code} {body})")
            try:
                req(f"/api/sessions/{s['key']}/model", token, {"model": "sonnet"})
                check("Modellwechsel abgewiesen", False, "(angenommen)")
            except urllib.error.HTTPError as e:
                check("Modellwechsel abgewiesen", e.code == 409, f"(HTTP {e.code})")

            # A restart must not make the phone's session "unknown", and a
            # client that counted past what the new bridge gave out must get
            # the new cards instead of waiting for the count to catch up.
            print("Neustart der Brücke")
            bridge.terminate()
            bridge.wait(timeout=15)
            bridge = start_bridge()
            for _ in range(40):
                try:
                    req("/api/health", token, timeout=1)
                    break
                except OSError:
                    time.sleep(0.25)
            try:
                _, d = req(f"/api/sessions/{s['key']}", token)
                check("Sitzung nach Neustart bekannt", d["session"]["key"] == s["key"])
                check("Beendet bleibt beendet", d["session"]["exited"] is True, f"({d['session']['exited']})")
            except urllib.error.HTTPError as e:
                check("Sitzung nach Neustart bekannt", False, f"(HTTP {e.code})")
            ghost = "t-" + "0" * 8 + "-0000-0000-0000-" + "0" * 12
            try:
                req(f"/api/sessions/{ghost}", token)
                check("Erfundene Sitzung bleibt unbekannt", False, "(gefunden)")
            except urllib.error.HTTPError as e:
                check("Erfundene Sitzung bleibt unbekannt", e.code == 404, f"(HTTP {e.code})")

        print("Freigabe vom Handy")
        _, a = req("/api/terminals/away", token, {"away": True})
        check("Unterwegs eingeschaltet", a["away"] is True)
        for allow, name in ((True, "ja.txt"), (False, "nein.txt")):
            p = claude(wd, f"Lege die Datei {name} mit dem Inhalt x an. "
                           "Antworte danach nur mit fertig.", env)
            s = wait_new(wd, token, seen, cond=lambda s: s["open_asks"] > 0,
                         timeout=120)
            label = "Erlauben" if allow else "Ablehnen"
            check(f"{label}: Anfrage kommt an", bool(s))
            if not s:
                p.kill()
                continue
            seen.add(s["claude_session_id"])
            _, d = req(f"/api/sessions/{s['key']}", token)
            ask = d["open_asks"][0]
            check(f"{label}: Werkzeug und Ziel lesbar",
                  ask["tool"] == "Write" and name in ask["detail"], f"({ask})")
            req(f"/api/sessions/{s['key']}/permission", token,
                {"request_id": ask["request_id"], "allow": allow})
            p.communicate(timeout=180)
            there = os.path.exists(os.path.join(wd, name))
            check(f"{label}: Datei {'geschrieben' if allow else 'fehlt'}",
                  there == allow)
        req("/api/terminals/away", token, {"away": False})

        print("Nachricht vom Handy")
        p = claude(wd, "Lies hallo.txt. Sag danach nur das Wort: eins.", env,
                   mode="acceptEdits")
        s = wait_new(wd, token, seen, timeout=60)
        check("Sitzung vor dem Zugende erkannt", bool(s))
        if s:
            seen.add(s["claude_session_id"])
            code, r = req(f"/api/sessions/{s['key']}/message", token,
                          {"text": "Sag jetzt zusätzlich nur das Wort: zwei."})
            check("Nachricht angenommen, nicht sofort zugestellt",
                  code == 202 and r.get("queued"), f"({code} {r})")
            out = p.communicate(timeout=180)[0]
            check("Claude hat sie ausgeführt", "zwei" in out.lower(), f"({out!r})")
            time.sleep(1.5)
            cards = backlog(s["key"], token)
            kinds = [c["kind"] for c in cards]
            check("Übergabe gemeldet", "delivered" in kinds, f"({kinds})")
            via = [c.get("via") for c in cards if c["kind"] == "delivered"]
            print(f"       übergeben per: {via}")
            sent = [c.get("text", "")[:80] for c in cards if c["kind"] == "sent"]
            print(f"       im Transcript als Eingabe: {sent}")
        else:
            p.kill()

        # The case that matters on the road: the session is already working
        # when the message comes in, so it has to go over at the end of the
        # turn. Queued before the prompt, it rides along with the prompt
        # instead - which is why this waits for 'busy' first.
        print("Nachricht am Zugende")
        p = claude(wd, "Lies hallo.txt, danach lies sie ein zweites Mal. "
                       "Sag erst dann nur das Wort: eins.", env, mode="acceptEdits")
        s = wait_new(wd, token, seen, cond=lambda s: s["busy"], timeout=90)
        check("Sitzung arbeitet schon", bool(s))
        if s:
            seen.add(s["claude_session_id"])
            code, r = req(f"/api/sessions/{s['key']}/message", token,
                          {"text": "Sag jetzt zusätzlich nur das Wort: drei."})
            check("Hinweis nennt das Zugende",
                  "Ende dieses Zugs" in r.get("note", ""), f"({r})")
            out = p.communicate(timeout=180)[0]
            check("Am Zugende ausgeführt", "drei" in out.lower(), f"({out!r})")
            time.sleep(1.5)
            cards = backlog(s["key"], token)
            via = [c.get("via") for c in cards if c["kind"] == "delivered"]
            check("Übergeben per Stop", "stop" in via, f"({via})")
            sent = [c.get("text", "")[:80] for c in cards if c["kind"] == "sent"]
            print(f"       im Transcript als Eingabe: {sent}")
            dones = [c for c in cards if c["kind"] == "done"]
            check("Genau ein Zugende, erst nach der Nachricht", len(dones) == 1,
                  f"({len(dones)})")
        else:
            p.kill()

        # The sentence before a tool call is the one the transcript loses;
        # MessageDisplay has it. And a command sent to the background has to
        # show up as running, not vanish once its call returned.
        print("Text und Hintergrund")
        p = claude(wd, "Schreib zuerst genau diesen Satz: 'Ich starte jetzt einen "
                       "Hintergrundbefehl.' Starte dann mit dem Bash-Werkzeug im Hintergrund "
                       "(run_in_background) den Befehl 'sleep 20'. Schließe mit genau: 'Ende.'",
                   env, mode="bypassPermissions")
        p.communicate(timeout=180)
        time.sleep(1.5)
        s = wait_new(wd, token, seen, timeout=10)
        check("Sitzung gemeldet", bool(s))
        if s:
            seen.add(s["claude_session_id"])
            cards = backlog(s["key"], token)
            says = [c.get("text", "") for c in cards if c["kind"] == "say"]
            check("Text vor dem Werkzeugaufruf kommt an",
                  any("Hintergrundbefehl" in t for t in says), f"({says})")
            check("Kein Text doppelt", len(says) == len(set(says)), f"({says})")
            bg = [c for c in cards if c["kind"] == "background"]
            check("Hintergrundaufgabe gemeldet",
                  any("sleep" in (t.get("command") or "") for c in bg for t in c.get("tasks") or []),
                  f"({bg[-1:] if bg else 'keine'})")
    finally:
        for p in SPAWNED:
            if p.poll() is None:
                p.kill()
        bridge.terminate()
        try:
            bridge.wait(timeout=10)
        except subprocess.TimeoutExpired:
            bridge.kill()
        shutil.rmtree(scratch, ignore_errors=True)

    print(f"\n{ok_count} ok, {len(fail)} fehlgeschlagen")
    if fail:
        print("  " + "\n  ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
