"""Thinking ahead as the app does it: draft at the first pause, the question
under the same id 1.5 s later; time from the final question to the first
recording, against the same question without a draft."""
import json, os, time, urllib.request
# On the PC: its own bridge and token from its config.
_cfg = json.load(open(os.path.expanduser("~/.config/iris/config.json"), encoding="utf-8-sig"))
B = f"http://127.0.0.1:{_cfg.get('port', 8780)}"
H = {"Authorization": "Bearer " + _cfg["token"], "Content-Type": "application/json"}
def post(b):
    return json.load(urllib.request.urlopen(urllib.request.Request(B + "/api/resident/talk", data=json.dumps(b).encode(), headers=H, method="POST"), timeout=20))
def wait_sound(gid, t0):
    txt = snd = None
    with urllib.request.urlopen(urllib.request.Request(B + "/api/resident/events?since=0", headers=H), timeout=90) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"): continue
            try: e = json.loads(line[5:])
            except ValueError: continue
            if e.get("id") != gid or (e.get("ts") or 0) < t0 - 1: continue
            if e.get("kind") == "antwort" and txt is None: txt = time.time() - t0
            if e.get("kind") == "stimme" and e.get("audio"): snd = time.time() - t0; break
            if time.time() - t0 > 80: break
    return txt, snd
for frage in ["Was ist dir heute Abend aufgefallen?", "Wie fühlt es sich an, nachts wach zu sein?"]:
    # with a draft
    gid = post({"text": frage, "draft": True, "von": "test"})["id"]
    time.sleep(1.5)
    t0 = time.time()
    post({"text": frage, "id": gid, "von": "test"})
    txt, snd = wait_sound(gid, t0)
    print(f"mit Entwurf   {frage[:40]:40}  Text {txt or -1:4.1f} s  erster Ton {snd or -1:4.1f} s")
    time.sleep(3)
    # without
    t0 = time.time()
    gid = post({"text": frage + " Sag es anders.", "von": "test"})["id"]
    txt, snd = wait_sound(gid, t0)
    print(f"ohne Entwurf  {frage[:40]:40}  Text {txt or -1:4.1f} s  erster Ton {snd or -1:4.1f} s")
    time.sleep(3)
