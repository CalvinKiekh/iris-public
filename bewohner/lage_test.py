"""Lagebild: Gerät verschwindet und kommt zurück, Netzfrage ohne Modell.

    python -X utf8 lage_test.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lage

JOURNAL = Path(__file__).parent / "werkstatt" / "journal.jsonl"
ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


# --- 1. Die Dienstantwort kommt ohne Modell ---
t0 = time.perf_counter()
antwort = lage.netz_antwort("Wer ist gerade im Netz?")
dauer = (time.perf_counter() - t0) * 1000
pruefen("Netzfrage ohne Modell beantwortet", bool(antwort), antwort or "")
pruefen("und zwar sofort", dauer < 200, f"{dauer:.0f} ms")

# --- 2. Verschwinden und Wiederkommen werden als Ereignis erkannt ---
#
# DIESER TEIL WAR SEIT EINER UMBENENNUNG TOT, und das ist am 12.09. nur
# aufgefallen, weil lage_test.py in einem Gesamtdurchlauf mitlief. Drei
# veraltete Stellen:
#
#   jetzt["geraete"]   das Feld heisst in lage.bauen() "netz"
#   "verschwunden"     unterschiede() schreibt "ist ... nicht mehr da"
#   "dazugekommen"     unterschiede() schreibt "ist ... im Netz aufgetaucht"
#
# Und der Grund, warum es niemand gemerkt hat: Der Test hat sein eigenes
# Scheitern WEGERKLAERT - "(kein Lagebild vorhanden - Bewohner laeuft
# nicht?)" und exit 1. Der Bewohner lief, das Lagebild war 30 Sekunden alt;
# nur der Feldname stimmte nicht. Ein Test, der eine plausible Entschuldigung
# ausgibt, statt zu scheitern, ist schlechter als einer, der scheitert.
# Deshalb sagt er jetzt, WAS er nicht gefunden hat.
jetzt = lage.lesen()
if not jetzt.get("netz"):
    print("  FAIL kein Lagebild: lage.json hat kein Feld 'netz' "
          "(%d Felder: %s)"
          % (len(jetzt), ", ".join(sorted(jetzt))[:120] or "keine"))
    sys.exit(1)

# Ein Geraet gilt erst nach FEHLT_BIS_WEG Blicken als weg - sonst meldet jeder
# verpasste Rundruf einen Abschied. Fuer das VORHER-Bild muss die Marke also
# gesetzt sein, sonst schweigt unterschiede() zu Recht.
eines = dict(jetzt["netz"][0])
eines["fehlt"] = lage.FEHLT_BIS_WEG
rest = [g for g in jetzt["netz"] if g["mac"] != jetzt["netz"][0]["mac"]]

vorher = {**jetzt, "netz": [eines] + rest}
nachher = {**jetzt, "netz": rest}

weg = lage.unterschiede(vorher, nachher)
pruefen("Verschwinden wird bemerkt",
        any("nicht mehr da" in z for z in weg),
        "; ".join(weg)[:80] or "(keine)")

zurueck = lage.unterschiede(nachher, vorher)
pruefen("Wiederkommen wird bemerkt",
        any("aufgetaucht" in z for z in zurueck),
        "; ".join(zurueck)[:80] or "(keine)")

# --- 3. Die Uhrzeit allein ist KEIN Ereignis ---
spaeter = dict(jetzt)
spaeter["uhrzeit"] = "23:59"
pruefen("Uhrzeitwechsel allein ist kein Ereignis",
        not lage.unterschiede(jetzt, spaeter),
        str(lage.unterschiede(jetzt, spaeter))[:60])

# --- 4. Der Bewohner schreibt das Lagebild laufend fort ---
alter = time.time() - float(jetzt.get("ts", 0))
pruefen("Lagebild ist frisch", alter < 120, f"{alter:.0f} s alt")

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
