"""Lässt Claude ein Werkzeug bauen und nimmt es ab.

    python -X utf8 werkzeug_bauen.py <name> "<zweck>"

Der Bewohner ist Dirigent: Er schreibt den Code nicht, er bestellt ihn,
prüft ihn und trägt ihn erst dann ein.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import werkzeuge
from chain import Bruecke

if len(sys.argv) < 3:
    sys.exit('Aufruf: werkzeug_bauen.py <name> "<zweck>"')
name, zweck = sys.argv[1], sys.argv[2]

print(f"Werkzeug: {name}\nZweck   : {zweck}\n")
auftrag = werkzeuge.auftrag_bauen(name, zweck)

b = Bruecke()
b.sitzung_sichern()
t0 = time.time()
antwort = b.beauftrage(auftrag)
print(f"Claude hat {time.time() - t0:.0f}s gebraucht:")
print(f"  {antwort[:300]}\n")

ok, grund = werkzeuge.pruefen(name)
print(f"Abnahme: {'bestanden' if ok else 'DURCHGEFALLEN'} - {grund}")

if ok:
    werkzeuge.eintragen(name, zweck, grund)
    print(f"\nIm Verzeichnis eingetragen. Jetzt benutzen:")
    lief, ausgabe = werkzeuge.benutzen(name)
    print(f"  {'lief' if lief else 'Fehler'}: {ausgabe[:300]}")
else:
    print("\nNicht eingetragen - was die Prüfung nicht besteht, wird nicht benutzt.")
sys.exit(0 if ok else 1)
