"""Der Gegentest des Macs, wörtlich: Termin entsteht, feuert einmal,
kein Auftrag, kein Timer.

    python -X utf8 f5_gegentest.py
"""
import json
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER / "werkstatt" / "werkzeuge"))
import erinnern  # noqa: E402

ZURUFE = HIER / "werkstatt" / "zurufe"
JOURNAL = HIER / "werkstatt" / "journal.jsonl"
SATZ = "Erinner mich in einer Minute an den Mac-Gegentest."
ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


def neue(ab):
    raus = []
    for z in JOURNAL.read_text(encoding="utf-8").splitlines()[ab:]:
        try:
            raus.append(json.loads(z))
        except json.JSONDecodeError:
            continue
    return raus


vorher = len(JOURNAL.read_text(encoding="utf-8").splitlines())
(ZURUFE / "gegentest.md").write_text(SATZ, encoding="utf-8")
print(f"Zuruf: {SATZ}\n  warte 30 s auf das Notieren ...")
time.sleep(30)

e = neue(vorher)
notiert = [x for x in e if x.get("kind") == "erinnerung"
           and "Gegentest" in str(x.get("text"))]
pruefen("als Termin notiert", bool(notiert),
        str(notiert[0]["text"])[:70] if notiert else "keine Zeile")

offen = [x for x in erinnern.lesen() if "Gegentest" in x.get("text", "")]
pruefen("steht in erinnerungen.json", bool(offen),
        str(offen[0]["wann"]) if offen else "Liste leer")

auftraege = [x for x in e if x.get("kind") == "auftrag"]
pruefen("KEIN Auftrag an Claude", not auftraege,
        str([str(a.get("text"))[:40] for a in auftraege]))

print("  warte, bis er fällig wird ...")
time.sleep(45)
e = neue(vorher)
gefeuert = [x for x in e if x.get("kind") == "erinnerung"
            and "wolltest an etwas erinnert" in str(x.get("text"))
            and "Gegentest" in str(x.get("text"))]
pruefen("genau einmal gefeuert", len(gefeuert) == 1,
        f"{len(gefeuert)} Mal")

time.sleep(40)
e = neue(vorher)
gefeuert2 = [x for x in e if x.get("kind") == "erinnerung"
             and "wolltest an etwas erinnert" in str(x.get("text"))
             and "Gegentest" in str(x.get("text"))]
pruefen("und auch danach nicht wieder", len(gefeuert2) == len(gefeuert),
        f"{len(gefeuert2)} Mal insgesamt")

auftraege = [x for x in neue(vorher) if x.get("kind") == "auftrag"]
pruefen("immer noch kein Auftrag", not auftraege)

# Aufräumen
rest = [x for x in erinnern.lesen() if "Gegentest" not in x.get("text", "")]
erinnern.schreiben(rest)
for p in ZURUFE.glob("gegentest*"):
    p.unlink(missing_ok=True)
for p in (ZURUFE / "gelesen").glob("gegentest*"):
    p.unlink(missing_ok=True)

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
