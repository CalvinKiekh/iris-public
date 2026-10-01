"""Probe: Der Bewohner kann eine Datei an Claude mitschicken.

    python -X utf8 anhang_test.py          nur die Riegel, ohne Netz
    python -X utf8 anhang_test.py --echt   dazu EIN echter Auftrag an Claude

DIESER TEST MUSS TRAGEN. Calvins Wort dazu: "Wenn ein Tool zum echten Testen
fehlt, bau dir eines. Ich will keine nicht tragenden Tests."

Also wird nicht geprueft, ob ein Feld gesetzt ist, sondern ob die Datei
WIRKLICH ANKOMMT: In sie wird eine Zeichenfolge geschrieben, die es sonst
nirgends gibt, und Claude wird gefragt, wie sie lautet. Kommt sie zurueck,
hat er die Datei gesehen. Kommt sie nicht, ist der Weg kaputt - und dann
faellt diese Probe durch, statt gruen zu leuchten.

Der echte Lauf kostet einen Zug bei Claude. Darum steht er hinter --echt.
"""
from __future__ import annotations

from einstellungen import NAMENS
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import probenort
from chain import Bruecke

GESAMT = 0
FEHLER = 0
HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


class NurHochladen(Bruecke):
    """Eine Bruecke, die nichts tut ausser den Riegel zu pruefen.

    `hochladen` bricht ab, bevor es das Netz braucht - so laesst sich die
    Grenze messen, ohne eine Sitzung zu belegen.
    """

    def __init__(self):
        self.token = "x"
        self.key = "t-probe"
        self.http = None                       # jeder Netzzugriff wuerfe

    def sitzung_sichern(self):                 # wird hier nie gebraucht
        return self.key


def probe_nur_aus_der_werkstatt() -> None:
    print("\nEr darf nur aus seiner Werkstatt mitschicken")
    b = NurHochladen()

    for pfad, warum in (
            (Path.home() / "Documents" / "geheim.txt", f"aus {NAMENS} Ordner"),
            (HIER / "bewohner.py", "aus dem Bau, nicht der Werkstatt"),
            (WERKSTATT / ".." / "chain.py", "ueber .. hinausgeklettert")):
        try:
            b.hochladen(pfad)
            pruefe(False, "durchgelassen: %s" % warum)
        except ValueError as f:
            pruefe("Werkstatt" in str(f) or "gibt es nicht" in str(f),
                   "abgelehnt (%s): %s" % (warum, str(f)[:60]))
        except Exception as f:
            pruefe(False, "falscher Fehler bei %s: %s" % (warum, type(f).__name__))


def probe_art_und_groesse() -> None:
    print("\nArt und Groesse werden geprueft, bevor etwas hochgeht")
    b = NurHochladen()
    ort = probenort.ablage("anhang")
    try:
        # Der Riegel haengt an der ECHTEN Werkstatt, nicht am Probenordner -
        # also wird hier in der Werkstatt gearbeitet und danach aufgeraeumt.
        proben = WERKSTATT / "_anhangprobe"
        proben.mkdir(exist_ok=True)
        exe = proben / "programm.exe"
        exe.write_bytes(b"MZ")
        try:
            b.hochladen(exe)
            pruefe(False, "eine .exe ging durch")
        except ValueError as f:
            pruefe("Art" in str(f), "eine .exe wird abgelehnt: %s" % str(f)[:50])

        gross = proben / "gross.txt"
        gross.write_bytes(b"x" * (b.ANHANG_MAX + 1))
        try:
            b.hochladen(gross)
            pruefe(False, "eine zu grosse Datei ging durch")
        except ValueError as f:
            pruefe("gross" in str(f), "zu gross wird abgelehnt: %s" % str(f)[:50])

        fehlt = proben / "gibtsnicht.txt"
        try:
            b.hochladen(fehlt)
            pruefe(False, "eine fehlende Datei ging durch")
        except ValueError as f:
            pruefe("gibt es nicht" in str(f), "fehlend wird abgelehnt")
    finally:
        import shutil
        shutil.rmtree(WERKSTATT / "_anhangprobe", ignore_errors=True)
        probenort.wegraeumen(ort)


def probe_misslungenes_steht_im_auftrag() -> None:
    print("\nEine Datei, die nicht mitging, wird GESAGT")
    gesendet = {}

    class Merkt(Bruecke):
        def __init__(self):
            self.token = "x"
            self.key = "t-probe"
            self.http = None

        def sitzung_sichern(self):
            return self.key

        def _get(self, pfad, **p):
            return {"session": {"seq": 0}}

        def _post(self, pfad, daten):
            gesendet.update(daten)
            return {}

        def hochladen(self, pfad):
            raise ValueError("nur aus der Werkstatt")

        def _strom_lesen(self, *a, **k):
            return ""

    b = Merkt()
    try:
        b.beauftrage("Sieh dir das an.", dateien=["C:/fremd.txt"])
    except Exception:
        pass                                    # der Strom faellt aus, egal
    text = gesendet.get("text", "")
    pruefe("NICHT mitschicken" in text,
           "der Auftrag sagt, dass die Datei fehlt: %s" % text[-90:])
    pruefe("attachments" not in gesendet,
           "und es wird kein leerer Anhang mitgeschickt")


def probe_echt() -> None:
    """EIN echter Zug: Datei hoch, Frage hin, Marke zurueck."""
    print("\nEchter Lauf: kennt Claude die Marke aus der Datei?")
    marke = "IRIS-" + secrets.token_hex(6).upper()
    proben = WERKSTATT / "_anhangprobe"
    proben.mkdir(exist_ok=True)
    datei = proben / "merkzettel.txt"
    datei.write_text(
        "Dies ist eine Probe der Bruecke.\n"
        "Die Pruefmarke lautet: %s\n"
        "Sonst steht hier nichts.\n" % marke, encoding="utf-8")
    print("  Marke in der Datei: %s" % marke)

    # EINE EIGENE SITZUNG, und die ist nicht Sparsamkeit, sondern Messung.
    #
    # Der erste Lauf am 14.09. nahm die gemerkte Sitzung des Bewohners - eine
    # mit langem Verlauf. Er hat 459 Sekunden gebraucht und 4,49 USD gekostet,
    # fuer eine Frage nach zwoelf Zeichen. Gemessen wird hier der WEG einer
    # Datei, nicht das Gedaechtnis einer Sitzung; alles andere ist Beiwerk,
    # das die Probe teuer und langsam macht und ihr Ergebnis verwaessert.
    b = Bruecke()
    eigene = b._post("/api/sessions",
                     {"cwd": str(WERKSTATT), "permission_mode": "auto"})
    b.key = eigene["session"]["key"]
    print("  eigene Sitzung: %s" % b.key)
    try:
        antwort = b.beauftrage(
            "Im Anhang liegt eine kurze Textdatei. Antworte mit NICHTS ausser "
            "der Pruefmarke, die darin steht. Keine Erklaerung, kein Satz.",
            dateien=[datei])
    finally:
        import shutil
        shutil.rmtree(proben, ignore_errors=True)
        # Die Sitzung wieder zumachen - eine Probe, die Sitzungen liegen
        # laesst, fuellt Calvins Uebersicht mit Muell.
        try:
            b._post(f"/api/sessions/{b.key}/close", {})
        except Exception:
            pass

    print("  Claude sagt: %s" % str(antwort)[:120].replace("\n", " "))
    pruefe(marke in str(antwort),
           "die Marke kommt zurueck - die Datei ist wirklich angekommen")


def main() -> int:
    probe_nur_aus_der_werkstatt()
    probe_art_und_groesse()
    probe_misslungenes_steht_im_auftrag()
    if "--echt" in sys.argv:
        probe_echt()
    else:
        print("\n(echter Lauf uebersprungen - mit --echt kostet er einen Zug)")
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
