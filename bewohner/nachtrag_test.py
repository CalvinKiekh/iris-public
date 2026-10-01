"""Nachtrag: Frage mit "zu", während die frühere noch denkt.

    python -X utf8 nachtrag_test.py

Erwartet: Der laufende Aufruf wird abgebrochen, beide Fragen werden ZUSAMMEN
beantwortet, und die abgebrochene Frage bleibt ohne halbe Antwort.
"""
import json
import sys
import time
from pathlib import Path

import pruefstand
pruefstand.braucht_bewohner()

GESPRAECH = Path(__file__).parent / "werkstatt" / "gespraech"
JOURNAL = Path(__file__).parent / "werkstatt" / "journal.jsonl"

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


def legen(text, kennung, zu=None):
    d = {"id": kennung, "ts": time.time(), "text": text,
         "status": "offen", "von": "test"}
    if zu:
        d["zu"] = zu
    (GESPRAECH / f"{kennung}.json").write_text(
        json.dumps(d, ensure_ascii=False), encoding="utf-8")


def lesen(kennung):
    try:
        return json.loads((GESPRAECH / f"{kennung}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


zeilen_vorher = len(JOURNAL.read_text(encoding="utf-8").splitlines())
erste = f"g-test-{int(time.time() * 1000)}"
# Eine Frage, über die er eine Weile nachdenkt - sonst ist sie fertig, bevor
# der Nachtrag überhaupt eintrifft (gpt-oss schafft 147 Token/s).
legen("Erzähl mir ausführlich, was du heute alles bemerkt und getan hast.",
      erste)
print(f"erste Frage gestellt ({erste})")

# Warten, bis er wirklich denkt - dann erst den Nachtrag.
gedacht = False
for _ in range(60):
    time.sleep(0.5)
    for z in JOURNAL.read_text(encoding="utf-8").splitlines()[zeilen_vorher:]:
        try:
            e = json.loads(z)
        except json.JSONDecodeError:
            continue
        if e.get("kind") == "frage" and e.get("id") == erste:
            gedacht = True
    if gedacht:
        break
pruefen("erste Frage wurde aufgenommen", gedacht)

time.sleep(0.4)
zweite = f"g-test-{int(time.time() * 1000)}"
legen("Und wie viel Platz ist noch frei?", zweite, zu=erste)
print(f"Nachtrag gestellt ({zweite}, zu {erste})")

ende = time.time() + 180
while time.time() < ende:
    time.sleep(0.5)
    if lesen(zweite).get("status") == "beantwortet":
        break

n = lesen(zweite)
e1 = lesen(erste)
antwort = n.get("antwort", "")
print(f"\nZusammen beantwortet:\n  {antwort[:200]}")

pruefen("Nachtrag ist beantwortet", n.get("status") == "beantwortet")
pruefen("die abgebrochene Frage hat keine fertige Antwort",
        e1.get("status") != "beantwortet", f"status={e1.get('status')}")

abbruch = any(
    json.loads(z).get("kind") == "nachtrag"
    for z in JOURNAL.read_text(encoding="utf-8").splitlines()[zeilen_vorher:]
    if z.strip())
pruefen("Abbruch steht im Journal", abbruch)

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
