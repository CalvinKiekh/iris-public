"""Key test through the PC bridge, as the app would do it (BEWOHNER.md, Beweis)."""
import json, os, subprocess, time, urllib.parse, urllib.request
# On the PC: its own bridge and token from its config. From the Mac: IRIS_URL and IRIS_TOKEN.
_cfg = {}
try:
    _cfg = json.load(open(os.path.expanduser("~/.config/iris/config.json"), encoding="utf-8-sig"))
except (OSError, ValueError):
    pass
B = os.environ.get("IRIS_URL") or f"http://127.0.0.1:{_cfg.get('port', 8780)}"
H = {"Authorization": "Bearer " + (os.environ.get("IRIS_TOKEN") or _cfg.get("token", "")), "Content-Type": "application/json"}
RESTART = 'Stop-ScheduledTask -TaskName "iris Bewohner"; Start-Sleep 3; Start-ScheduledTask -TaskName "iris Bewohner"'

ok_all = []

def get(p):
    return json.load(urllib.request.urlopen(urllib.request.Request(B + p, headers=H), timeout=20))

def post(p, body):
    r = urllib.request.Request(B + p, data=json.dumps(body).encode(), headers=H, method="POST")
    try:
        return json.load(urllib.request.urlopen(r, timeout=20))
    except urllib.error.HTTPError as e:
        return json.load(e)

def check(name, cond, extra=""):
    ok_all.append(bool(cond))
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if extra else ""), flush=True)

def facts(q, replaced=False):
    return get("/api/resident/memory?art=fakt&q=" + urllib.parse.quote(q) + ("&replaced=1" if replaced else ""))

def wait(fn, secs):
    end = time.time() + secs
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(2)
    return None

def ask(text, secs=120):
    t0 = time.time()
    gid = post("/api/resident/talk", {"text": text, "von": "test"}).get("id")
    if not gid:
        return None, 0
    req = urllib.request.Request(B + "/api/resident/events?since=0", headers=H)
    with urllib.request.urlopen(req, timeout=secs) as resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            try:
                e = json.loads(line[5:])
            except ValueError:
                continue
            if e.get("kind") == "antwort" and e.get("id") == gid:
                return e.get("text") or "", time.time() - t0
            if time.time() - t0 > secs:
                break
    return None, time.time() - t0

def answer_whole(text, secs=120):
    # sentence by sentence: the 'antwort' line holds the first; wait a little for the rest
    return ask(text, secs)

print("1. merken", flush=True)
post("/api/resident/say", {"text": "Merk dir, dass der Schlüssel im Flur liegt."})
f = wait(lambda: [m for m in facts("Schlüssel")["memories"] if "Flur" in m["text"]], 90)
check("Fakt steht im Gedächtnis (wie die App ihn sieht)", f, f and f[0]["text"])
flur = f[0]["id"] if f else None

print("2. Neustart, dann fragen", flush=True)
st = get("/api/resident")["resident"]
print("   Zustand vorher:", st.get("state"), "alive", st.get("alive"), flush=True)
def _pc():
    """Der PC aus IRIS_PC oder ../rechner.env - vom Mac aus gebraucht."""
    pc = os.environ.get("IRIS_PC")
    if not pc:
        try:
            for z in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "rechner.env"), encoding="utf-8"):
                if z.strip().startswith("IRIS_PC="):
                    pc = z.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    if not pc:
        raise SystemExit("IRIS_PC fehlt - in rechner.env eintragen (Vorlage: rechner.env.beispiel)")
    return pc


subprocess.run(["powershell", "-NoProfile", "-Command", RESTART] if os.name == "nt" else ["ssh", _pc(), RESTART], check=False)
t_restart = time.time()
alive = wait(lambda: (lambda s: s.get("alive") and (s.get("seen") or 0) > t_restart)(get("/api/resident")["resident"]), 180)
check("Bewohner nach Neustart wieder wach", alive, f"{time.time() - t_restart:.0f} s")
a, secs = ask("Wo liegt der Schlüssel?")
check("weiß nach Neustart: im Flur", a and "flur" in a.lower(), f"{a!r} nach {secs:.1f} s")

print("3. ersetzen", flush=True)
post("/api/resident/say", {"text": "Merk dir, dass der Schlüssel jetzt in der Küche liegt."})
k = wait(lambda: [m for m in facts("Schlüssel")["memories"] if "Küche" in m["text"] or "Kueche" in m["text"]], 90)
check("neuer Fakt Küche steht", k, k and k[0]["text"])
kueche = k[0]["id"] if k else None
live = [m for m in facts("Schlüssel")["memories"] if "Flur" in m["text"]]
check("alter Fakt Flur gilt nicht mehr (nicht doppelt)", not live, str([m["text"] for m in live]))
if flur:
    chain = get("/api/resident/memory?id=" + flur).get("chain", [])
    check("Flur zeigt auf Küche (ersetzt_durch)", len(chain) >= 2 and chain[1]["id"] == kueche, str([c["text"] for c in chain]))
a, secs = ask("Wo liegt der Schlüssel?")
check("antwortet: Küche", a and ("küche" in a.lower() or "kueche" in a.lower()) and "flur" not in a.lower(), f"{a!r} nach {secs:.1f} s")

print("4. vergessen über die App-Schnittstelle", flush=True)
if kueche:
    r = post("/api/resident/memory", {"id": kueche, "aktion": "vergessen"})
    check("Änderung angenommen", r.get("ok"), str(r.get("error") or ""))
    gone = wait(lambda: not get("/api/resident/memory")["pending"] and not [m for m in facts("Schlüssel")["memories"] if m["id"] == kueche], 60)
    check("vom Bewohner übernommen, Fakt weg", gone)
    a, secs = ask("Wo liegt der Schlüssel?")
    low = (a or "").lower()
    check("weiß es nicht mehr (weder Küche noch Flur)", a is not None and "küche" not in low and "kueche" not in low and "flur" not in low, f"{a!r} nach {secs:.1f} s")

    # Nothing may be left elsewhere either: not in a memory of any kind.
    rest = [m for m in get("/api/resident/memory?limit=300")["memories"] if "küche" in m["text"].lower() or "kueche" in m["text"].lower()]
    check("keine andere Erinnerung trägt die Küche weiter", not rest, str([(m["art"], m["text"][:60]) for m in rest]))

print("5. Zeiten", flush=True)
t0 = time.time(); get("/api/resident/memory?q=Schl%C3%BCssel"); t1 = time.time() - t0
check("App-Suche über die Brücke", t1 < 1.5, f"{t1*1000:.0f} ms inkl. Netz")
print(f"\n{sum(ok_all)} ok, {len(ok_all) - sum(ok_all)} fehlgeschlagen", flush=True)
