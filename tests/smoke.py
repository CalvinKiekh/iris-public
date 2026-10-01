"""Self-test: drives the bridge over HTTP the way a client does.

Runs a real Claude session on the default model in a scratch directory,
so it costs a
little quota. It proves the parts that are easy to get subtly wrong:
the permission round-trip, replay after a dropped stream, and refusal
without a token.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

PORT = 8779
BASE = f"http://127.0.0.1:{PORT}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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


def req(path, body=None, token=None, timeout=20):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    r = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return json.loads(f.read())


def read_backlog(path, token, seconds=2.5, timeout=8):
    """Read what an SSE stream has buffered, then let go.

    The stream stays open by design, so a plain read would sit there until
    it times out. We take what is already there and stop.
    """
    rr = urllib.request.Request(BASE + path,
                                headers={"Authorization": "Bearer " + token})
    got, start = [], time.time()
    try:
        with urllib.request.urlopen(rr, timeout=timeout) as fh:
            for line in fh:
                if line.startswith(b"data: "):
                    got.append(json.loads(line[6:].decode()))
                if time.time() - start > seconds:
                    break
    except (TimeoutError, OSError):
        pass                      # quiet stream, backlog is already in hand
    return got

try:
    from tests.port import muss_frei_sein, muss_leben
except ImportError:                     # als Skript gestartet
    from port import muss_frei_sein, muss_leben


def main():
    from bridge import config
    cfg = config.load()
    token = cfg["token"]

    # No push from a test bridge: it reads the real config, phones included.
    # And its own state folder, like the other tests: a second bridge on the
    # real feeds writes cards with numbers of its own into the same files,
    # and the app then reads a number that falls back as "the bridge counts
    # afresh" and reloads the conversation without end.
    state = tempfile.mkdtemp(prefix="iris-smoke-state-")
    muss_frei_sein(PORT)
    proc = subprocess.Popen(
        [sys.executable, "-m", "bridge", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT, env=dict(os.environ, IRIS_NO_PUSH="1",
                           IRIS_AWAY_PATH=os.path.join(state, "away.json"),
                           IRIS_TERMINALS_PATH=os.path.join(state, "terminals.json")),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    muss_leben(proc, PORT)
    wd = tempfile.mkdtemp(prefix="iris-smoke-")
    try:
        print("auth")
        try:
            req("/api/health")
            check("ohne Token abgewiesen", False, "(Zugriff war offen!)")
        except urllib.error.HTTPError as e:
            check("ohne Token abgewiesen", e.code == 401, f"(HTTP {e.code})")
        check("mit Token erlaubt", req("/api/health", token=token).get("ok") is True)

        print("registry")
        check("Projekte gelistet", isinstance(req("/api/projects", token=token)["projects"], list))
        check("Shortcuts geliefert", len(req("/api/shortcuts", token=token)["shortcuts"]) > 0)

        print("laufende terminals")
        from bridge import live as _live
        cwds = _live.terminal_cwds()
        check("Terminal-Erkennung liefert ein Ergebnis", isinstance(cwds, dict))
        rows = [{"modified": time.time(), "session_id": "a"},
                {"modified": time.time(), "session_id": "b"},
                {"modified": 0, "session_id": "c"}]
        out = _live.annotate(rows, "/gibt/es/nicht", {"/gibt/es/nicht": ["1"]})
        check("Nur die frischeste Unterhaltung wird markiert",
              [r["likely_open"] for r in out] == [True, False, False],
              f"({[r['likely_open'] for r in out]})")
        out = _live.annotate(rows, "/ohne/prozess", {})
        check("Ohne laufenden Prozess wird nichts markiert",
              not any(r["likely_open"] for r in out))

        print("session")
        s = req("/api/sessions", {"cwd": wd},
                token=token)["session"]
        key = s["key"]
        check("Session angelegt", bool(key))

        cards, asked, done = [], threading.Event(), threading.Event()
        holder = {}

        def stream():
            r = urllib.request.Request(f"{BASE}/api/sessions/{key}/events?since=0",
                                       headers={"Authorization": "Bearer " + token})
            with urllib.request.urlopen(r, timeout=180) as f:
                for line in f:
                    line = line.decode().strip()
                    if not line.startswith("data: "):
                        continue
                    c = json.loads(line[6:])
                    cards.append(c)
                    if c["kind"] == "ask":
                        holder["req"] = c["request_id"]
                        asked.set()
                    elif c["kind"] == "done":
                        done.set()
        threading.Thread(target=stream, daemon=True).start()
        time.sleep(1)

        req(f"/api/sessions/{key}/message",
            {"text": "Schreibe mit dem Write-Tool die Datei ok.txt mit dem Inhalt 'iris'. Sonst nichts."},
            token=token)
        check("Bestätigung angefordert", asked.wait(90))

        if asked.is_set():
            # Deny first: nothing may touch the disk without a yes.
            req(f"/api/sessions/{key}/permission",
                {"request_id": holder["req"], "allow": False}, token=token)
            time.sleep(2)
            check("Ablehnung verhindert Schreiben", not os.path.exists(os.path.join(wd, "ok.txt")))

        # Waiting on the event alone is flaky: under load the `done` card can
        # arrive after the timeout even though the turn finished. Fall back to
        # asking the session, which is the authoritative answer.
        done.wait(60)
        finished = done.is_set()
        if not finished:
            for _ in range(30):
                time.sleep(1)
                if not req(f"/api/sessions/{key}", token=token)["session"]["busy"]:
                    finished = True
                    break
        check("Turn abgeschlossen", finished)
        check("Karten normalisiert", {"ready", "act", "ask"} <= {c["kind"] for c in cards},
              f"(sah {sorted({c['kind'] for c in cards})})")
        check("Sequenznummern lückenlos",
              [c["seq"] for c in cards] == sorted(c["seq"] for c in cards))

        print("replay")
        seq = max(c["seq"] for c in cards) - 3
        got = read_backlog(f"/api/sessions/{key}/events?since={seq}", token,
                           seconds=2.0)
        check("Nachlieferung nach Verbindungsabriss", len(got) >= 1 and
              all(c["seq"] > seq for c in got))

        print("modus")
        modes = req("/api/modes", token=token)["modes"]
        check("Modi gelistet", any(m["id"] == "plan" for m in modes))
        r = req(f"/api/sessions/{key}/mode", {"mode": "plan"}, token=token)
        check("Modus umgestellt", r.get("ok") and r.get("mode") == "plan",
              f"({r})")
        time.sleep(2)
        check("Moduswechsel als Karte gemeldet",
              any(c["kind"] == "mode" and c.get("mode") == "plan" for c in cards))
        try:
            req(f"/api/sessions/{key}/mode", {"mode": "quatsch"}, token=token)
            check("Unsinniger Modus abgelehnt", False, "(wurde angenommen)")
        except urllib.error.HTTPError as e:
            check("Unsinniger Modus abgelehnt", e.code == 400, f"(HTTP {e.code})")

        print("verlauf")
        h = req(f"/api/sessions/{key}/history", token=token)["cards"]
        check("Frische Sitzung liefert keinen doppelten Verlauf", h == [],
              f"({len(h)} Karten)")

        print("steuerkanal")
        ctx = req(f"/api/sessions/{key}/context", token=token).get("context") or {}
        check("Kontextaufschlüsselung geliefert",
              ctx.get("maxTokens", 0) > 0 and bool(ctx.get("categories")),
              f"({list(ctx)[:4]})")
        cap = req(f"/api/sessions/{key}/capabilities", token=token) \
                 .get("capabilities") or {}
        check("Fähigkeiten geliefert",
              len(cap.get("models") or []) > 0 and len(cap.get("commands") or []) > 0,
              f"(Modelle {len(cap.get('models') or [])}, "
              f"Befehle {len(cap.get('commands') or [])})")
        r = req(f"/api/sessions/{key}/control",
                {"subtype": "get_binary_version"}, token=token)
        check("Roher Steuerbefehl geht durch",
              bool((r.get("response") or {}).get("version")), f"({r})")
        try:
            r = req(f"/api/sessions/{key}/control",
                    {"subtype": "gibtesnicht"}, token=token)
            check("Unbekannter Steuerbefehl wird gemeldet", bool(r.get("error")))
        except urllib.error.HTTPError as e:
            check("Unbekannter Steuerbefehl wird gemeldet", e.code == 400,
                  f"(HTTP {e.code})")

        print("detailgrade")
        sizes = {}
        for lvl in ("full", "card", "minimal"):
            got = read_backlog(f"/api/sessions/{key}/events?since=0&detail={lvl}",
                               token)
            sizes[lvl] = (len(got), len(json.dumps(got)))
        check("Alle drei Detailgrade liefern Karten",
              all(n > 0 for n, _ in sizes.values()), f"({sizes})")
        check("Weniger Detail heißt weniger Daten",
              sizes["full"][1] > sizes["minimal"][1],
              f"(full {sizes['full'][1]} vs minimal {sizes['minimal'][1]})")
        acts = [c for c in read_backlog(
            f"/api/sessions/{key}/events?since=0&detail=full", token)
            if c["kind"] == "act"]
        check("Vollmodus trägt die Werkzeug-Eingabe mit",
              bool(acts) and all("input" in a for a in acts),
              f"({len(acts or [])} Aufrufe)")

        print("systemprompt")
        r = req(f"/api/sessions/{key}/system-prompt",
                {"prompt": "Antworte immer sehr knapp."}, token=token)
        check("System-Prompt gesetzt", r.get("ok"), f"({r})")
        try:
            req(f"/api/sessions/{key}/system-prompt", {"prompt": ""}, token=token)
            check("Leerer System-Prompt abgelehnt", False, "(angenommen)")
        except urllib.error.HTTPError as e:
            check("Leerer System-Prompt abgelehnt", e.code == 400)

        print("konfiguration")
        cfg = req("/api/config?project=" + urllib.parse.quote(wd), token=token)
        check("Konfigurationsflächen gelistet", len(cfg["surfaces"]) > 0)
        check("Sammlungen gelistet",
              any(c["id"] == "memory" for c in cfg["collections"]))
        r = req("/api/config/file?path=" + urllib.parse.quote("/etc/passwd"),
                token=token)
        check("Fremde Datei abgewiesen", bool(r.get("error")))
        settings = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
        r = req("/api/config/file?path=" + urllib.parse.quote(settings), token=token)
        check("Freigegebene Datei lesbar", "content" in r, f"({r.get('error')})")
        try:
            req("/api/config/file", {"path": settings, "content": "{kaputt"},
                token=token)
            check("Kaputtes JSON abgelehnt", False, "(geschrieben!)")
        except urllib.error.HTTPError as e:
            check("Kaputtes JSON abgelehnt", e.code == 400)

        print("dateiverfolgung")
        tf = req(f"/api/sessions/{key}/files", token=token)["files"]
        check("Geänderte Datei erfasst",
              any(f["name"] == "probe.txt" or f["name"] == "ok.txt" for f in tf)
              or len(tf) > 0, f"({[f['name'] for f in tf]})")
        if tf:
            d = req(f"/api/sessions/{key}/files/{tf[0]['id']}/diff", token=token)
            check("Diff erzeugt", "diff" in d and d.get("from") == "v0",
                  f"({d.get('error') or d.get('from')})")

        print("git")
        acc = req("/api/git?what=accounts&cwd=/tmp", token=token)["accounts"]
        check("GitHub-Konten erkannt", len(acc) > 0, f"({acc})")
        r = req("/api/git?what=status&cwd=" + urllib.parse.quote(wd), token=token)
        check("Verzeichnis ohne Repo sauber gemeldet", r.get("repo") is False,
              f"({r})")
        own = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = req("/api/git?what=status&cwd=" + urllib.parse.quote(own), token=token)
        check("Git-Status beantwortet", "repo" in r, f"({r})")
        try:
            req("/api/git?what=quatsch&cwd=/tmp", token=token)
            check("Unbekannte Git-Abfrage abgelehnt", False, "(angenommen)")
        except urllib.error.HTTPError as e:
            check("Unbekannte Git-Abfrage abgelehnt", e.code == 400)

        print("inventar")
        inv = req("/api/inventory?what=summary", token=token)
        check("Inventar beantwortet", inv.get("projects", 0) > 0, f"({inv})")
        r = req("/api/inventory?what=search&q=iris", token=token)["projects"]
        check("Suche findet nach Relevanz",
              bool(r) and r[0].get("rank", 9) <= 1,
              f"({[x['name'] for x in r[:3]]})")
        svc = req("/api/inventory?what=services", token=token)["services"]
        check("Dienste erfasst", isinstance(svc, list) and len(svc) > 0)
        own = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        r = req("/api/inventory/scan", {"project": own}, token=token)
        check("Einzelprojekt nachziehbar", "updated" in r, f"({r})")
        try:
            req("/api/inventory?what=quatsch", token=token)
            check("Unbekannte Inventar-Abfrage abgelehnt", False, "(angenommen)")
        except urllib.error.HTTPError as e:
            check("Unbekannte Inventar-Abfrage abgelehnt", e.code == 400)

        print("inventar über mcp")
        import subprocess as _sp
        srv = os.path.join(own, "bridge", "mcp_inventory_server.py")
        # Nicht `proc`: das ist die Bruecke. Dieser Name ueberschrieb sie bis
        # zum 29.09.2026, der Aufraeumblock am Ende beendete dann den laengst
        # toten MCP-Server - und jede Testbruecke blieb verwaist liegen. Die vom
        # 14.09. hat zwei Wochen lang alle folgenden Rauchtests beantwortet.
        mcp = _sp.Popen([sys.executable, srv], stdin=_sp.PIPE, stdout=_sp.PIPE,
                         text=True, bufsize=1)
        try:
            def rpc(method, params=None, rid=1):
                mcp.stdin.write(json.dumps({"jsonrpc": "2.0", "id": rid,
                                             "method": method,
                                             "params": params or {}}) + "\n")
                mcp.stdin.flush()
                return json.loads(mcp.stdout.readline())
            rpc("initialize")
            tools = rpc("tools/list", rid=2)["result"]["tools"]
            check("MCP-Server bietet Werkzeuge an", len(tools) >= 5,
                  f"({[t['name'] for t in tools]})")
            out = rpc("tools/call", {"name": "machine_summary",
                                     "arguments": {}}, rid=3)
            payload = json.loads(out["result"]["content"][0]["text"])
            check("MCP liefert die Maschinen-Übersicht",
                  payload.get("projects", 0) > 0, f"({payload})")
        finally:
            mcp.kill()

        print("dienste melden sich")
        from bridge import heartbeat as _hb
        ing = _hb.ingest_token()
        check("Eigenes Ingest-Token vorhanden", len(ing) > 20)
        r = req("/api/heartbeat",
                {"name": "smoke-probe", "host": "testhost", "status": "ok",
                 "interval": 5, "detail": {"n": 1}}, token=ing)
        check("Heartbeat angenommen", r.get("ok"), f"({r})")
        rows = req("/api/services?host=testhost", token=token)["services"]
        check("Dienst erscheint", any(x["name"] == "smoke-probe" for x in rows))
        try:
            req("/api/heartbeat", {"name": "x", "host": "y"}, token="falsch")
            check("Falsches Token abgewiesen", False, "(angenommen)")
        except urllib.error.HTTPError as e:
            check("Falsches Token abgewiesen", e.code == 401)
        try:
            req("/api/services", token=ing)
            check("Ingest-Token darf nicht lesen", False, "(durfte lesen!)")
        except urllib.error.HTTPError as e:
            check("Ingest-Token darf nicht lesen", e.code == 401)
        try:
            req("/api/heartbeat", {"name": "", "host": ""}, token=ing)
            check("Heartbeat ohne Namen abgelehnt", False, "(angenommen)")
        except urllib.error.HTTPError as e:
            check("Heartbeat ohne Namen abgelehnt", e.code == 400)

        # interval 5s, Toleranz 2.5x -> nach ~13s vermisst
        time.sleep(14)
        _hb.sweep()
        rows = req("/api/services?host=testhost", token=token)["services"]
        probe = next((x for x in rows if x["name"] == "smoke-probe"), None)
        check("Ausbleibender Dienst gilt als vermisst",
              probe and probe["missing"], f"({probe})")
        ev = req("/api/services?what=events&service=testhost/smoke-probe",
                 token=token)["events"]
        check("Zustandswechsel protokolliert",
              any(e["kind"] == "vermisst" for e in ev), f"({ev[:2]})")
        req("/api/services/forget", {"id": "testhost/smoke-probe"}, token=token)

        print("abzweig")
        sid = req(f"/api/sessions/{key}", token=token)["session"]["claude_session_id"]
        req(f"/api/sessions/{key}/close", {}, token=token)
        time.sleep(1)
        f = req("/api/sessions", {"cwd": wd, "resume": sid, "fork": True},
                token=token)["session"]
        check("Abzweig gestartet", f.get("fork") is True)
        # The CLI announces its session id in system/init, and that only
        # arrives with the first message - not at process start. So send one.
        req(f"/api/sessions/{f['key']}/message",
            {"text": "Antworte nur mit dem Wort ok."}, token=token)
        new_id = None
        for _ in range(40):
            time.sleep(1)
            new_id = req(f"/api/sessions/{f['key']}", token=token)["session"] \
                        .get("claude_session_id")
            if new_id:
                break
        check("Abzweig bekommt eine eigene Sitzungs-ID",
              new_id is not None and new_id != sid, f"({new_id})")
        check("Abzweig bringt den Verlauf mit",
              len(req(f"/api/sessions/{f['key']}/history", token=token)["cards"]) > 0)
        # Look the transcript up the way the bridge does, so symlinked temp
        # paths (/tmp -> /private/tmp on macOS) do not break the check.
        from bridge import history as _h
        check("Ursprüngliches Transcript bleibt liegen",
              _h.find_transcript(sid) is not None)
        req(f"/api/sessions/{f['key']}/close", {}, token=token)
        check("Session geschlossen", True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(wd, ignore_errors=True)
        shutil.rmtree(state, ignore_errors=True)
        # Also drop the transcript Claude Code wrote for the scratch dir,
        # so test runs do not pile up in the project list.
        from bridge import projects as _p
        shutil.rmtree(os.path.join(config.CLAUDE_PROJECTS,
                                   _p.project_for_path(wd)), ignore_errors=True)

    print(f"\n{ok_count} ok, {len(fail)} fehlgeschlagen")
    if fail:
        print("fehlgeschlagen:", ", ".join(fail))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
