"""Vergessen darf nur mitnehmen, was denselben INHALT trägt.

Beim Vergessen von neun Testfragen ist Calvins echte Frage von 22:00
mitgelöscht worden - sie klang nur ähnlich. Dieser Test hält das fest.

    python -X utf8 kaskade_test.py
"""
from einstellungen import NAME
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gedaechtnis as g
import probenort

# EIGENE ABLAGE. Diese Probe legte ihre Kaskadenproben bis zum 13.09. ins
# echte gedaechtnis.db und raeumte sie danach mit `vergessen()` weg - und
# genau das Wegraeumen ist der Fehler, den sie selbst misst: Beim Vergessen
# von neun Testfragen ist Calvins echte Frage von 22:00 mitgegangen, weil sie
# nur aehnlich klang. Eine Probe, die im Echten loescht, kann diesen Fehler
# jederzeit wiederholen.
ORDNER = probenort.ablage("kaskade")
g.WERKSTATT = ORDNER
g.DATENBANK = ORDNER / "gedaechtnis.db"
g.KERNWISSEN = ORDNER / "ERINNERUNG.md"
g.AENDERUNGEN = ORDNER / "aenderungen"

ok_alle = []


def pruefen(name: str, bedingung: bool, dazu: str = "") -> None:
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}"
          + (f"  [{dazu}]" if dazu else ""))


g.anlegen()
# `with sqlite3.connect(...)` schliesst NICHT - es beendet nur die
# Transaktion. Auf Modulebene bliebe die Verbindung damit bis zum Programmende
# offen, und unter Windows scheitert das Wegraeumen des Probenordners dann mit
# WinError 32.
def alle_kennungen(wo: str = ""):
    """Lesen und die Verbindung WIRKLICH schliessen."""
    v = g._verbindung()
    try:
        return [int(r[0]) for r in v.execute(
            "SELECT id FROM erinnerung" + wo).fetchall()]
    finally:
        v.close()


alt = alle_kennungen(" WHERE text LIKE '%Kaskadenprobe%'")
for k in alt:
    g.vergessen(k)

# Zwei Gespräche, die sich ÄHNLICH anhören, aber nichts miteinander zu tun haben.
a = g.merken("gespraech", f"Kaskadenprobe eins. {NAME} fragte: Kannst du mich "
                          "hören? Ich antwortete: Ja, ich höre dich.",
             quelle="Probe")
b = g.merken("gespraech", f"Kaskadenprobe zwei. {NAME} fragte: Kann ich jetzt "
                          "vernünftig mit dir reden? Ich antwortete: Ja, "
                          "das geht.", quelle="Probe")
print(f"zwei ähnliche Gespräche angelegt: #{a} und #{b}")

geloescht = g.vergessen(a)
print(f"#{a} vergessen, dabei {len(geloescht)} Text(e) entfernt\n")

noch_da = alle_kennungen()

pruefen("das vergessene Gespräch ist weg", a not in noch_da)
pruefen("das ähnliche Gespräch bleibt", b in noch_da,
        "sonst löscht Vergessen fremde Erinnerungen mit")

# Gegenprobe: Ein Fakt UND ein Gespräch, das ihn wörtlich trägt.
f = g.fakt_merken("Merk dir, dass die Kaskadenprobe im Keller liegt.", "Probe")[0]
gx = g.merken("gespraech", f"{NAME} fragte: Wo ist die Kaskadenprobe? "
                           "Ich antwortete: Die Kaskadenprobe liegt im Keller.",
              quelle="Probe")
g.vergessen(f)
noch_da = alle_kennungen()
pruefen("Gespräch, das den vergessenen Fakt wörtlich trägt, geht mit",
        gx not in noch_da)

for k in (b,):
    g.vergessen(k)
# Was gedaechtnis selbst noch offen haelt, gibt der Sammler frei - sonst
# haelt die letzte Verbindung die Datei fest.
import gc  # noqa: E402

gc.collect()
probenort.wegraeumen(ORDNER)
print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
