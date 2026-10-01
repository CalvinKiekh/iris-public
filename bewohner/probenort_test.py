"""Der Riegel selbst - die Probe, die den 12.09. nachstellt.

Wenn diese Probe durchfaellt, kann eine andere Probe die Werkstatt loeschen.

    python -X utf8 probe_test.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import probenort

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}"
          + (f"  [{dazu}]" if dazu else ""))


def verweigert(pfad) -> bool:
    """Lehnt der Riegel das ab?"""
    try:
        probenort.wegraeumen(pfad)
        return False
    except probenort.Verweigert:
        return True


# --------------------------------------------------- 1. Der Fall vom 12.09.
print("\nDer Fall vom 12.09.: die Probe hat frisch() vergessen")

echt = probenort.ECHTE_WERKSTATT
vorher_da = echt.exists()
pruefen("die echte Werkstatt liegt da", vorher_da, str(echt))

pruefen("der Riegel lehnt die echte Werkstatt ab", verweigert(echt))
pruefen("und sie liegt danach immer noch da", echt.exists())
pruefen("darf_weg() sagt dasselbe, ohne etwas zu tun",
        probenort.darf_weg(echt) is False)

# Auch das, was die Werkstatt ENTHAELT - ein `rmtree(WERKSTATT.parent)` waere
# noch schlimmer.
for gefaehrlich in (echt.parent, echt.parent.parent, Path(echt.anchor)):
    pruefen(f"abgelehnt: {gefaehrlich}", verweigert(gefaehrlich))

# Und einzelne echte Dateien.
for datei in ("gedaechtnis.db", "journal.jsonl", "ICH.md"):
    p = echt / datei
    abgelehnt = False
    try:
        probenort.datei_weg(p)
    except probenort.Verweigert:
        abgelehnt = True
    pruefen(f"abgelehnt: werkstatt\\{datei}", abgelehnt)
    if datei == "gedaechtnis.db":
        pruefen("  und sie liegt noch da", p.exists())


# ------------------------------------------------ 2. Was erlaubt sein MUSS
print("\nWas eine Probe darf")

ordner = probenort.ablage("riegel")
pruefen("ablage() gibt einen frischen Ordner", ordner.is_dir(), str(ordner))
pruefen("und er liegt unter WURZEL", probenort.WURZEL in ordner.parents)
pruefen("nie unter der Werkstatt", echt not in ordner.parents)

(ordner / "etwas.txt").write_text("x", encoding="utf-8")
(ordner / "tiefer").mkdir()
(ordner / "tiefer" / "noch etwas.txt").write_text("x", encoding="utf-8")
pruefen("darf_weg() laesst ihn durch", probenort.darf_weg(ordner) is True)
pruefen("auch einen Unterordner", probenort.darf_weg(ordner / "tiefer") is True)
probenort.wegraeumen(ordner)
pruefen("wegraeumen() hat ihn geraeumt", not ordner.exists())

# Zwei Ablagen sind verschieden - keine Probe raeumt der anderen weg.
a, b = probenort.ablage("eins"), probenort.ablage("zwei")
pruefen("zwei Ablagen sind zwei Ordner", a != b)
probenort.wegraeumen(a)
pruefen("die eine ist weg, die andere nicht",
        not a.exists() and b.exists())
probenort.wegraeumen(b)

# Ein nicht vorhandener Pfad unter WURZEL ist kein Fehler.
probenort.wegraeumen(probenort.WURZEL / "gibt-es-nicht")
pruefen("ein nicht vorhandener Probenpfad ist kein Fehler", True)


# ------------------------------- 3. Die gewachsenen Ordner in der Werkstatt
print("\nDie Probenordner, die es in der Werkstatt schon gibt")

gewachsen = echt / "_riegel_probe"
gewachsen.mkdir(exist_ok=True)
(gewachsen / "x.txt").write_text("x", encoding="utf-8")
pruefen("werkstatt\\_riegel_probe darf weg (Unterstrich)",
        probenort.darf_weg(gewachsen) is True)
probenort.wegraeumen(gewachsen)
pruefen("und ist weg", not gewachsen.exists())

# Aber NICHT die echten Unterordner der Werkstatt.
for echter in ("werkzeuge", "gedaechtnis", "sitzungen", "eingang", "antraege"):
    pruefen(f"abgelehnt: werkstatt\\{echter} (kein Unterstrich)",
            verweigert(echt / echter))
pruefen("werkzeuge liegen noch da",
        (echt / "werkzeuge").exists() and
        len(list((echt / "werkzeuge").glob("*.py"))) >= 10,
        f"{len(list((echt / 'werkzeuge').glob('*.py')))} Werkzeuge")

# Und nicht tiefer als eine Ebene - werkstatt\werkzeuge\_x ist nicht
# "ein Probenordner der Werkstatt".
pruefen("abgelehnt: werkstatt\\werkzeuge\\_tief",
        probenort.darf_weg(echt / "werkzeuge" / "_tief") is False)


# --------------------------------------------------- 4. Alles andere auch
print("\nAlles ausserhalb")

for fremd in (Path.home(), Path.home() / "Desktop", Path.home() / "Downloads",
              Path(__file__).parent, Path(__file__)):
    pruefen(f"abgelehnt: {fremd}", probenort.darf_weg(fremd) is False)

# Auch ueber einen Umweg nicht.
pruefen("abgelehnt: auch mit .. im Pfad",
        probenort.darf_weg(probenort.WURZEL / ".." / ".." / "Windows") is False)


# ------------------------------------------- 5. Der Riegel fuers SCHREIBEN
#
# Das Gegenstueck zu darf_weg, und es hat genauso lange gefehlt. Eine Probe
# konnte die Werkstatt seit dem 12.09. nicht mehr loeschen, aber ungehindert
# ins echte Gedaechtnis SCHREIBEN. pruefung_test.py tat es bei jedem Lauf:
# siebzehn Erinnerungen an "Lenas Arzttermin" lagen am Morgen des 13.09. im
# echten gedaechtnis.db, aus einer Sitzung, die Calvin nie gefuehrt hat.
print("\nDer Riegel fuers Schreiben")

pruefen("diese Probe erkennt sich selbst als Probe",
        probenort.eine_probe_laeuft())
pruefen("ins echte Gedaechtnis darf sie nicht",
        probenort.darf_schreiben(echt / "gedaechtnis.db") is False)
pruefen("und auch nicht tiefer hinein",
        probenort.darf_schreiben(echt / "sitzungen" / "s-1.json") is False)
pruefen("und nicht in die Werkstatt selbst",
        probenort.darf_schreiben(echt) is False)

_eigene = probenort.ablage("riegel")
try:
    pruefen("in ihre eigene Ablage dagegen schon",
            probenort.darf_schreiben(_eigene / "gedaechtnis.db") is True)
    probenort.schreiben_pruefen(_eigene / "g.db")
    pruefen("und schreiben_pruefen laesst sie durch", True)
finally:
    probenort.wegraeumen(_eigene)

try:
    probenort.schreiben_pruefen(echt / "gedaechtnis.db", "merken(fakt)")
    pruefen("schreiben_pruefen wirft bei der echten Ablage", False)
except probenort.Verweigert as _f:
    pruefen("schreiben_pruefen wirft und sagt, was es war",
            "ECHTE Ablage" in str(_f) and "merken(fakt)" in str(_f))

# Und der Riegel sitzt wirklich in gedaechtnis.merken, nicht nur hier.
import gedaechtnis

_vorher = gedaechtnis.DATENBANK
gedaechtnis.DATENBANK = echt / "gedaechtnis.db"
try:
    gedaechtnis.merken("fakt", "Diese Zeile darf NIE im Echten landen.")
    pruefen("gedaechtnis.merken ist verriegelt", False)
except probenort.Verweigert:
    pruefen("gedaechtnis.merken ist verriegelt", True)
finally:
    gedaechtnis.DATENBANK = _vorher


print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
