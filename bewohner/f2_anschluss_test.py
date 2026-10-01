"""Hört er wirklich hin, oder rät er? Frage mit Aufnahme.

    python -X utf8 f2_anschluss_test.py
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


def stellen(text, aufnahme):
    kennung = f"g-test-{int(time.time() * 1000)}"
    (GESPRAECH / f"{kennung}.json").write_text(json.dumps(
        {"id": kennung, "ts": time.time(), "text": text, "status": "offen",
         "von": "test", "aufnahme": aufnahme}, ensure_ascii=False),
        encoding="utf-8")
    ende = time.time() + 180
    while time.time() < ende:
        time.sleep(0.3)
        try:
            d = json.loads((GESPRAECH / f"{kennung}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("status") == "beantwortet":
            return kennung, d.get("antwort", "")
    return kennung, "(Zeitlimit)"


zeilen_vorher = len(JOURNAL.read_text(encoding="utf-8").splitlines())

for wav, erwartet_hz in (("g-1789167392636.wav", 168),
                         ("g-1789138221090.wav", 108)):
    if not (GESPRAECH / wav).exists():
        print(f"  ({wav} fehlt - übersprungen)")
        continue
    print(f"\nFrage mit {wav}:")
    kennung, antwort = stellen("Wie klinge ich gerade?", wav)
    print(f"  {antwort[:220]}")

    neu = JOURNAL.read_text(encoding="utf-8").splitlines()[zeilen_vorher:]
    gehoert = [json.loads(z) for z in neu
               if z.strip() and json.loads(z).get("kind") == "gehoert"
               and json.loads(z).get("id") == kennung]
    pruefen("es wurde gemessen (gehoert im Journal)", bool(gehoert),
            gehoert[0]["text"][:80] if gehoert else "keine Zeile")
    if gehoert:
        pruefen("gemessene Tonhöhe stimmt",
                abs(gehoert[0]["tonhoehe_hz"] - erwartet_hz) < 15,
                f"{gehoert[0]['tonhoehe_hz']:.0f} Hz erwartet {erwartet_hz}")
    pruefen("die Antwort nennt Zahlen",
            any(c.isdigit() for c in antwort), antwort[:60])

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
