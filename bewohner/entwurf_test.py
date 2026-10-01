"""Entwürfe werden nie beantwortet - erst wenn Calvin sie abschickt.

    python -X utf8 entwurf_test.py
"""
import json
import sys
import time
from pathlib import Path

import pruefstand
pruefstand.braucht_bewohner("gespraech")

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


kennung = f"g-test-{int(time.time() * 1000)}"
schreiben(kennung, "Wie viel Platz ist noch frei?", "entwurf")
print(f"Entwurf gelegt ({kennung}) - 25 s warten\n")
time.sleep(25)

d = lesen(kennung)
pruefen("Entwurf wurde nicht beantwortet", not d.get("antwort"),
        f"antwort={str(d.get('antwort'))[:40]}")
pruefen("Status ist unverändert entwurf", d.get("status") == "entwurf",
        f"status={d.get('status')}")

print("\njetzt abschicken (status offen)")
schreiben(kennung, "Wie viel Platz ist noch frei?", "offen")
ende = time.time() + 120
while time.time() < ende:
    time.sleep(0.5)
    if lesen(kennung).get("status") == "beantwortet":
        break

d = lesen(kennung)
pruefen("nach dem Abschicken beantwortet", d.get("status") == "beantwortet",
        f"status={d.get('status')}")
print(f"   -> {str(d.get('antwort'))[:90]}")

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
