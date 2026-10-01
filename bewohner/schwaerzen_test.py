"""Schwärzt das Vergessen nur noch den Satz - und nur bei wörtlichem Treffer?

    python -X utf8 schwaerzen_test.py
"""
from einstellungen import NAMENS
import json
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
import bewohner  # noqa: E402

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


# Auf einer Kopie arbeiten, das echte Journal bleibt unberührt.
probe = HIER / "werkstatt" / "_schwaerz_probe.jsonl"
echt = bewohner.JOURNAL
bewohner.JOURNAL = probe

ZEILEN = [
    {"ts": time.time(), "kind": "zuruf",
     "text": "Merk dir, dass der Schlüssel im Flur liegt. Danke dir."},
    {"ts": time.time(), "kind": "auftrag", "id": "g-1",
     "text": "Prüfe den Platz auf C und melde das Ergebnis."},
    {"ts": time.time(), "kind": "fund",
     "text": "Der Schlüssel liegt im Flur."},
    {"ts": time.time(), "kind": "pause",
     "text": "Auftrag zurückgehalten: du arbeitest gerade selbst."},
]
probe.write_text("\n".join(json.dumps(z, ensure_ascii=False)
                          for z in ZEILEN) + "\n", encoding="utf-8")

n = bewohner.journal_saeubern(["Der Schlüssel liegt im Flur."])
print(f"{n} Zeilen angefasst\n")

raus = [json.loads(z) for z in probe.read_text(encoding="utf-8").splitlines()]
for e in raus:
    print(f"  {e['kind']:8} {e['text'][:70]}")

pruefen("nur die betroffenen Zeilen", n == 2, f"{n}")
pruefen("der Zuruf behält seinen Rest",
        "Danke dir" in raus[0]["text"], raus[0]["text"][:50])
pruefen("der Inhalt ist weg", "Flur" not in raus[0]["text"])
pruefen("der unbeteiligte Auftrag bleibt ganz",
        raus[1]["text"] == "Prüfe den Platz auf C und melde das Ergebnis.")
pruefen("die Art bleibt erkennbar", all(e.get("kind") for e in raus))
pruefen("bleibt nichts übrig, wird es benannt",
        raus[2]["text"] == f"Inhalt auf {NAMENS} Wunsch entfernt",
        raus[2]["text"])
pruefen("die Pause blieb unberührt", "zurückgehalten" in raus[3]["text"])

# Gegenprobe: ähnliche Wörter, aber nicht wörtlich -> nichts schwärzen
probe.write_text(json.dumps(
    {"ts": time.time(), "kind": "fund",
     "text": "Der Ersatzschlüssel liegt beim Nachbarn."},
    ensure_ascii=False) + "\n", encoding="utf-8")
n = bewohner.journal_saeubern(["Der Schlüssel liegt im Flur."])
pruefen("nur Ähnlichkeit schwärzt NICHT", n == 0, f"{n} Zeilen")

bewohner.JOURNAL = echt
probe.unlink(missing_ok=True)
print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
