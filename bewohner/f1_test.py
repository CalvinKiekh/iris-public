"""F1 SEHEN: Bildschirm und ein echtes Foto.

    python -X utf8 f1_test.py
"""
import einstellungen
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "werkstatt" / "werkzeuge"))
import werkzeuge

ok_alle = []


def am_bildschirm() -> bool:
    """Laeuft diese Probe ueberhaupt dort, wo es einen Bildschirm gibt?

    Windows trennt Sitzungen: An der Konsole sitzt Sitzung 1, ein SSH-Zugang
    bekommt Sitzung 0 - und die HAT keinen Desktop. Wer die Probe von aussen
    startet, kann nichts aufnehmen, egal wie gut das Werkzeug ist.

    Das war keine graue Theorie: Diese Probe meldete tagelang "Bildschirm
    nicht aufnehmbar", und sie wurde jedes Mal als Umgebungsfehler abgehakt.
    Der Bewohner selbst laeuft in Sitzung 1 und sieht den Bildschirm - am
    14.09. um 01:32 nachgemessen, er hat den Texteditor im Vordergrund
    beschrieben. Kaputt war also nie das Werkzeug, sondern der Ort der Probe.

    Eine Probe, die am Ort scheitert, darf nicht "fehlgeschlagen" sagen. Sie
    muss sagen, dass sie hier nicht messen kann - sonst verdeckt ein dauerhaft
    rotes Feld irgendwann einen echten Ausfall.
    """
    try:
        import ctypes
        sid = ctypes.c_ulong()
        ctypes.windll.kernel32.ProcessIdToSessionId(
            ctypes.windll.kernel32.GetCurrentProcessId(), ctypes.byref(sid))
        return sid.value != 0
    except Exception:
        return True          # Kein Windows, keine Sitzungstrennung.


if not am_bildschirm():
    print("F1 SEHEN: uebersprungen.")
    print("  Diese Probe laeuft in Windows-Sitzung 0 - dort gibt es keinen")
    print("  Desktop, also nichts aufzunehmen. Das ist kein Fehler des")
    print("  Werkzeugs: Der Bewohner laeuft in Sitzung 1 und sieht den")
    print("  Bildschirm. Zum Messen die Probe an der Konsole starten, oder")
    print("  den Bewohner fragen: \"Was siehst du auf dem Bildschirm?\"")
    print("\n0 von 0 bestanden")
    raise SystemExit(0)


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


print("Abnahme durch den Bewohner:")
ok, grund = werkzeuge.pruefen("sehen")
pruefen("bestanden", ok, grund[:120])

print("\nEin echtes Foto ansehen:")
import sehen

fotos = [p for p in einstellungen.DESKTOP.glob("*")
         if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
if fotos:
    satz = sehen.ansehen(fotos[0])
    print(f"  {fotos[0].name}: {satz[:150]}")
    pruefen("Foto beschrieben", len(satz) > 20 and
            sum(c.isalpha() for c in satz) / max(len(satz), 1) > 0.6)
else:
    print("  (kein Foto auf dem Desktop - übersprungen)")

print("\nBildschirm ansehen:")
satz = sehen.blick()
print(f"  {satz[:180]}")
# ZUERST: Ist ueberhaupt etwas aufgenommen worden? Vorher stand hier nur
# `len(satz) > 20`, und daran ist die falsche Abnahme entstanden, die am
# 12.09. in werkzeuge.json stand:
#
#   "geprueft": true,
#   "ergebnis": "Selbsttest bestanden: 2 KB aufgenommen, beschrieben als:
#                Das Bild ist leer. Kein Programm im Vordergrund."
#
# Der Fehlschlagsatz ist 74 Zeichen lang, hat fuenf lange Woerter und keine
# Auszeichnungen - er bestand also ALLE drei Pruefungen, und danach wurde
# `sehen` als geprueft eingetragen. Eine Laenge sagt nichts darueber, ob
# etwas zu sehen war; dieselbe Verwechslung wie `st_size > 1000` in
# bildschirm_aufnehmen().
pruefen("Bildschirm wirklich aufgenommen",
        satz != sehen.NICHT_AUFGENOMMEN, satz[:70])
pruefen("Bildschirm beschrieben", len(satz) > 20)
pruefen("in ganzen Wörtern",
        len([w for w in satz.split() if len(w) > 3]) >= 5, satz[:50])
pruefen("ohne Auszeichnungen", not any(z in satz for z in "*`#"))

if all(ok_alle):
    werkzeuge.eintragen(
        "sehen",
        "Sieht den Bildschirm an und beschreibt in einem Satz, was darauf zu "
        "sehen ist", grund)
    print("\nEingetragen. Was er jetzt kann:")
    for z in werkzeuge.liste():
        print(f"  {z}")

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
