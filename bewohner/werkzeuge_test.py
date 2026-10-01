"""Der Bewohner nimmt Werkzeuge ab - auch solche, die durchfallen müssen.

    python -X utf8 werkzeuge_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import werkzeuge

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


print("Abnahme eines Werkzeugs, das durchfallen muss:")
ok, grund = werkzeuge.pruefen("boeser_helfer")
pruefen("abgelehnt", not ok, grund)
pruefen("mit nachvollziehbarem Grund",
        any(w in grund for w in ("löscht", "Netz", "fremde")), grund)
pruefen("nicht im Verzeichnis",
        "boeser_helfer" not in werkzeuge.verzeichnis_lesen())

print("\nAbnahme eines brauchbaren Werkzeugs:")
ok, grund = werkzeuge.pruefen("platzverlauf")
pruefen("angenommen", ok, grund)

if ok:
    werkzeuge.eintragen("platzverlauf",
                        "Hält den freien Platz auf C fest und nennt den Trend",
                        grund)
    pruefen("im Verzeichnis eingetragen",
            "platzverlauf" in werkzeuge.verzeichnis_lesen())

    print("\nUnd benutzen:")
    lief, ausgabe = werkzeuge.benutzen("platzverlauf")
    pruefen("läuft", lief, ausgabe[:80])
    lief2, ausgabe2 = werkzeuge.benutzen("platzverlauf")
    pruefen("beim zweiten Mal ein Trend", lief2 and "Gigabyte" in ausgabe2,
            ausgabe2[:80])

    print("\nWas er jetzt kann:")
    for z in werkzeuge.liste():
        print(f"  {z}")

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
