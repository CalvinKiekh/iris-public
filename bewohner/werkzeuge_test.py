"""Der Bewohner nimmt Werkzeuge ab - auch solche, die durchfallen müssen.

    python -X utf8 werkzeuge_test.py

In einer Wegwerf-Werkstatt, mit zwei Werkzeugen, die die Probe selbst
schreibt: eines, das durchfallen muss, und eines, das bestehen muss. Das
echte Verzeichnis werkzeuge.json bleibt unberuehrt - frueher trug diese
Probe dort platzverlauf neu ein, und das boese Werkzeug lag als Datei in
der echten Werkstatt.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import probenort
import werkzeuge

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


BOESE = '''import shutil
shutil.rmtree("irgendwo")
'''

# Counts its calls in a file next to itself - so the second call can tell
# a first from a second, as a tool with a history would.
ZAEHLER = '''import sys
from pathlib import Path

DATEI = Path(__file__).resolve().parent.parent / "zaehler.txt"


def main():
    if "--selbsttest" in sys.argv:
        print("Selbsttest bestanden")
        return 0
    n = int(DATEI.read_text()) + 1 if DATEI.exists() else 1
    DATEI.write_text(str(n))
    print("Aufruf Nummer %d" % n)
    return 0


raise SystemExit(main())
'''

echt = (werkzeuge.WERKSTATT, werkzeuge.ORDNER, werkzeuge.VERZEICHNIS)
ort = probenort.ablage("werkzeuge")
werkzeuge.WERKSTATT = ort
werkzeuge.ORDNER = ort / "werkzeuge"
werkzeuge.VERZEICHNIS = ort / "werkzeuge.json"
werkzeuge.ORDNER.mkdir()
(werkzeuge.ORDNER / "boeser_helfer.py").write_text(BOESE, encoding="utf-8")
(werkzeuge.ORDNER / "zaehler.py").write_text(ZAEHLER, encoding="utf-8")

try:
    print("Abnahme eines Werkzeugs, das durchfallen muss:")
    ok, grund = werkzeuge.pruefen("boeser_helfer")
    pruefen("abgelehnt", not ok, grund)
    pruefen("mit nachvollziehbarem Grund",
            any(w in grund for w in ("löscht", "Netz", "fremde")), grund)
    pruefen("nicht im Verzeichnis",
            "boeser_helfer" not in werkzeuge.verzeichnis_lesen())

    print("\nEines, das es nicht gibt:")
    ok, grund = werkzeuge.pruefen("gibtsnicht")
    pruefen("abgelehnt, weil die Datei fehlt", not ok and "gibt es nicht" in grund, grund)

    print("\nAbnahme eines brauchbaren Werkzeugs:")
    ok, grund = werkzeuge.pruefen("zaehler")
    pruefen("angenommen", ok, grund)

    werkzeuge.eintragen("zaehler", "Zaehlt, wie oft es gerufen wurde", grund)
    pruefen("im Verzeichnis eingetragen",
            "zaehler" in werkzeuge.verzeichnis_lesen())

    print("\nUnd benutzen:")
    lief, ausgabe = werkzeuge.benutzen("zaehler")
    pruefen("läuft", lief and "Nummer 1" in ausgabe, ausgabe[:80])
    lief2, ausgabe2 = werkzeuge.benutzen("zaehler")
    pruefen("beim zweiten Mal weiß es vom ersten", lief2 and "Nummer 2" in ausgabe2,
            ausgabe2[:80])
    lief3, ausgabe3 = werkzeuge.benutzen("boeser_helfer")
    pruefen("was nicht eingetragen ist, wird nicht benutzt",
            not lief3 and "nicht im Verzeichnis" in ausgabe3, ausgabe3[:80])

    print("\nWas er jetzt kann:")
    for z in werkzeuge.liste():
        print(f"  {z}")
finally:
    werkzeuge.WERKSTATT, werkzeuge.ORDNER, werkzeuge.VERZEICHNIS = echt
    probenort.wegraeumen(ort)

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
