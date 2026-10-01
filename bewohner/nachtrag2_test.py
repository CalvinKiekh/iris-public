"""Nachtrag NACH dem ersten gesprochenen Satz - der Fall vom Mac.

    python -X utf8 nachtrag2_test.py

Der Nachtrag muss wissen, was eben gesagt wurde, auch wenn nichts davon im
Verlauf steht (Testfragen landen dort absichtlich nicht).
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


erste = f"g-test-{int(time.time() * 1000)}"
legen("Nenne mir deine Lieblingsfarbe und begründe sie ausführlich.", erste)
print(f"erste Frage gestellt ({erste})")

# Warten, bis der ERSTE Satz gesprochen ist - dann erst der Nachtrag.
gesagt = ""
ende = time.time() + 90
while time.time() < ende:
    time.sleep(0.2)
    d = lesen(erste)
    if d.get("antwort"):
        gesagt = d["antwort"]
        break
pruefen("erster Satz war heraus, bevor der Nachtrag kam", bool(gesagt),
        gesagt[:60])

zweite = f"g-test-{int(time.time() * 1000)}"
legen("Und welche Zahl magst du?", zweite, zu=erste)
print(f"Nachtrag gestellt ({zweite})")

ende = time.time() + 180
while time.time() < ende:
    time.sleep(0.3)
    if lesen(zweite).get("status") == "beantwortet":
        break

n, e1 = lesen(zweite), lesen(erste)
antwort = n.get("antwort", "")
print(f"\nAntwort auf den Nachtrag:\n  {antwort[:220]}")

pruefen("Nachtrag ist beantwortet", n.get("status") == "beantwortet")
pruefen("die frühere Frage hängt nicht auf 'antwortet'",
        e1.get("status") == "beantwortet", f"status={e1.get('status')}")
# Er soll die Farbe kennen, ohne sie zu wiederholen - also mindestens etwas
# zur Zahl sagen und nicht bei null anfangen.
pruefen("der Nachtrag nennt eine Zahl",
        any(z in antwort for z in "0123456789") or
        any(w in antwort.lower() for w in
            ("eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben",
             "acht", "neun", "zehn", "null")),
        antwort[:60])

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
