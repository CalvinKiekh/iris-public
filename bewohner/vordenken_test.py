"""Vordenken: Entwurf schicken, dann absenden - wie viel schneller?

    python -X utf8 vordenken_test.py

Vergleicht zwei gleichartige Fragen: eine ohne Entwurf, eine mit.
"""
import json
import sys
import time
from pathlib import Path

GESPRAECH = Path(__file__).parent / "werkstatt" / "gespraech"
ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


def schreiben(kennung, text, status):
    (GESPRAECH / f"{kennung}.json").write_text(json.dumps(
        {"id": kennung, "ts": time.time(), "text": text,
         "status": status, "von": "test"}, ensure_ascii=False),
        encoding="utf-8")


def lesen(kennung):
    try:
        return json.loads((GESPRAECH / f"{kennung}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def warten(kennung, frist=180.0):
    """Zeit bis zur ersten MP3 - das ist der erste Ton."""
    t0 = time.time()
    while time.time() - t0 < frist:
        time.sleep(0.1)
        if list(GESPRAECH.glob(f"{kennung}-*.mp3")):
            return time.time() - t0
    return None


FRAGE = "Erklär mir kurz, warum du nachts wach bleibst."

# --- ohne Entwurf ---
a = f"g-test-{int(time.time() * 1000)}"
schreiben(a, FRAGE, "offen")
ohne = warten(a)
while lesen(a).get("status") != "beantwortet" and time.time() < time.time() + 60:
    time.sleep(0.3)
    if lesen(a).get("status") == "beantwortet":
        break
print(f"ohne Entwurf : erster Ton nach {ohne:.1f}s" if ohne else "ohne: kein Ton")

time.sleep(2)

# --- mit Entwurf: erst als entwurf, 6 s denken lassen, dann absenden ---
b = f"g-test-{int(time.time() * 1000)}"
schreiben(b, FRAGE, "entwurf")
print("Entwurf gelegt, 8 s Vordenken ...")
time.sleep(8)
d = lesen(b)
pruefen("Entwurf wurde nicht beantwortet", not d.get("antwort"))
pruefen("keine MP3 zum Entwurf", not list(GESPRAECH.glob(f"{b}-*.mp3")))

schreiben(b, FRAGE, "offen")
mit = warten(b)
ende = time.time() + 120
while time.time() < ende:
    time.sleep(0.3)
    if lesen(b).get("status") == "beantwortet":
        break
print(f"mit Entwurf  : erster Ton nach {mit:.1f}s" if mit else "mit: kein Ton")
print(f"   -> {str(lesen(b).get('antwort'))[:90]}")

if ohne and mit:
    pruefen("mit Entwurf schneller zum ersten Ton", mit < ohne,
            f"{mit:.1f}s gegen {ohne:.1f}s")

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
