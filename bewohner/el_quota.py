import json, pathlib, urllib.request, datetime
key = pathlib.Path.home().joinpath(".config", "iris", "elevenlabs.key").read_text().strip()
req = urllib.request.Request("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key})
try:
    d = json.load(urllib.request.urlopen(req, timeout=15))
except Exception as e:
    print("Fehler:", type(e).__name__, str(getattr(e, "code", "")))
    raise SystemExit
reset = d.get("next_character_count_reset_unix")
print(json.dumps({
    "tarif": d.get("tier"),
    "verbraucht": d.get("character_count"),
    "grenze": d.get("character_limit"),
    "zuruecksetzung": datetime.datetime.fromtimestamp(reset).strftime("%d.%m.%Y") if reset else None,
    "stimmklon_instant": d.get("can_use_instant_voice_cloning"),
    "status": d.get("status"),
}, ensure_ascii=False))
