"""F5: Zuruf wird zum Termin, und er meldet sich, wenn es soweit ist.

    python -X utf8 f5_test.py
"""
import json
import sys
import time
from pathlib import Path

import pruefstand
pruefstand.braucht_bewohner()
pruefstand.braucht_werkzeug("erinnern")

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER / "werkstatt" / "werkzeuge"))
import erinnern  # noqa: E402
from bewohner import ERINNERUNGSZURUF  # noqa: E402

ZURUFE = HIER / "werkstatt" / "zurufe"
JOURNAL = HIER / "werkstatt" / "journal.jsonl"
ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


print("Der Zuruf wird als Termin erkannt:")
for satz, soll in (
        ("Erinner mich um 18:30 an die Mülltonne", True),
        ("Erinnere mich in 5 Minuten an den Ofen", True),
        ("Merk dir, dass der Schlüssel im Flur liegt", False),
        ("Prüfe bitte den Platz auf C", False)):
    ist = bool(ERINNERUNGSZURUF.match(satz))
    pruefen(f"{'Termin' if soll else 'kein Termin'}: {satz[:40]}", ist == soll)

print("\nIm Betrieb:")
zeilen_vorher = len(JOURNAL.read_text(encoding="utf-8").splitlines())
(ZURUFE / "f5test.md").write_text(
    "Erinnere mich in 1 Minuten an den Testtermin.", encoding="utf-8")
print("  Zuruf gelegt, warte auf das Notieren ...")

notiert = None
ende = time.time() + 90
while time.time() < ende:
    time.sleep(2)
    for z in JOURNAL.read_text(encoding="utf-8").splitlines()[zeilen_vorher:]:
        try:
            e = json.loads(z)
        except json.JSONDecodeError:
            continue
        if e.get("kind") == "erinnerung" and "Testtermin" in str(e.get("text")):
            notiert = e
            break
    if notiert:
        break
pruefen("als Termin notiert", bool(notiert),
        str(notiert.get("text"))[:70] if notiert else "keine Zeile")

if notiert:
    print("  warte, bis er fällig wird ...")
    gemeldet = None
    ende = time.time() + 150
    while time.time() < ende:
        time.sleep(3)
        for z in JOURNAL.read_text(encoding="utf-8").splitlines()[zeilen_vorher:]:
            try:
                e = json.loads(z)
            except json.JSONDecodeError:
                continue
            if (e.get("kind") == "erinnerung"
                    and "wolltest an etwas erinnert" in str(e.get("text"))):
                gemeldet = e
                break
        if gemeldet:
            break
    pruefen("zur rechten Zeit gemeldet", bool(gemeldet),
            str(gemeldet.get("text"))[:70] if gemeldet else "keine Meldung")

# Aufräumen: meine Testtermine wieder weg. Diese Probe schreibt als einzige
# ins Echte, und zwar um etwas WEGZUNEHMEN - den Termin hat der laufende
# Bewohner angelegt, nicht sie. Der Riegel in erinnern.schreiben() wird dafür
# ausdrücklich und benannt geöffnet.
import probenort  # noqa: E402

liste = [e for e in erinnern.lesen() if "Testtermin" not in e.get("text", "")]
with probenort.ausnahme("f5_test raeumt seine eigenen Testtermine weg"):
    erinnern.schreiben(liste)

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
