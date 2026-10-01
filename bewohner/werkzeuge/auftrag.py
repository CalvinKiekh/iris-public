"""auftrag - einen Auftrag an Claude formulieren und die Antwort abnehmen.

    python auftrag.py --pruefen "Text"   taugt der Auftrag etwas?
    python auftrag.py --selbsttest

Der Bewohner kann Claude beauftragen - das ist die Bruecke. Was ihm fehlte,
war die Sorgfalt DAVOR und DANACH:

  davor   Ein Auftrag muss fuer sich stehen. Claude kennt das Gespraech nicht,
          kennt die Werkstatt nicht und hat kein Gedaechtnis davon. "Mach das
          fertig" ist kein Auftrag.
  danach  Eine Antwort ist kein Beweis. "Erledigt" ist eine Behauptung, bis
          er es selbst nachgesehen hat.

Dieses Werkzeug entscheidet nicht, OB beauftragt wird - das tut die Bremse -,
sondern ob der Auftrag TAUGT und was danach zu pruefen ist.

Pfade haengen am Ort dieser Datei. Nur Standardbibliothek, kein Netz.
"""

import argparse
import json
import os
import re
import sys

WERKZEUG_ORDNER = os.path.dirname(os.path.abspath(__file__))
WERKSTATT_ORDNER = os.path.dirname(WERKZEUG_ORDNER)

# Woerter, die nur im Gespraech Sinn ergeben. Claude kennt das Gespraech nicht.
ZEIGEWOERTER = re.compile(
    r"\b(das\s+(nochmal|noch\s*mal|wieder|fertig)|mach\s+weiter|"
    r"wie\s+besprochen|wie\s+eben|dasselbe|das\s+gleiche|"
    r"den\s+rest|weiter\s+so|siehe\s+oben)\b", re.IGNORECASE)

# Ohne ein Tunwort ist es kein Auftrag, sondern eine Bemerkung.
TUNWOERTER = re.compile(
    r"\b(erstell|schreib|baue?|leg|aendere|ändere|pruefe|prüfe|suche|finde|"
    r"lies|entferne|verschiebe|ergaenze|ergänze|repariere|richte|"
    r"installiere|messe|zeige|nenne|fasse|untersuche|starte)\w*\b",
    re.IGNORECASE)

MINDESTZEICHEN = 25


def pruefen(text):
    """Taugt der Auftrag? Gibt (ja/nein, Begruendung) zurueck."""
    text = " ".join(str(text).split())
    # Der Verweis zuerst: "Mach das nochmal fertig" ist auch zu kurz, aber
    # der eigentliche Mangel ist, dass Claude nicht weiss, was "das" ist.
    # Die genauere Begruendung hilft mehr als die allgemeine.
    treffer = ZEIGEWOERTER.search(text)
    if treffer:
        return False, ("verweist auf etwas, das Claude nicht kennt (%r) - "
                       "der Auftrag muss für sich stehen" % treffer.group(0))
    if len(text) < MINDESTZEICHEN:
        return False, ("zu kurz - Claude kennt den Zusammenhang nicht und "
                       "kann daraus nichts machen")
    if not TUNWOERTER.search(text):
        return False, ("es fehlt, was getan werden soll - eine Beschreibung "
                       "ist noch kein Auftrag")
    return True, "steht für sich"


def pruefung_vorschlagen(auftrag):
    """Woran liesse sich das Ergebnis UNABHAENGIG erkennen?

    Nicht an Claudes Antwort - die ist eine Behauptung. An etwas, das man
    danach selbst nachsehen kann.
    """
    text = str(auftrag).lower()
    pfade = re.findall(r"[A-Za-z]:\\[^\s\"']+|werkstatt[\\/][^\s\"']+", text)
    if pfade:
        return {"art": "datei_existiert", "pfad": pfade[0],
                "text": "gibt es %s danach wirklich?" % pfade[0]}
    if "ordner" in text or "verzeichnis" in text:
        return {"art": "ordner_zaehlt", "pfad": WERKSTATT_ORDNER,
                "mindestens": 1,
                "text": "liegt danach etwas in der Werkstatt?"}
    return {"art": "keine",
            "text": ("dieser Auftrag hinterlässt keine Spur, die ich "
                     "nachsehen könnte")}


def zerlegen(wunsch):
    """Aus einem groben Wunsch mehrere Auftraege machen - einer je Schritt.

    Ein Auftrag, der drei Dinge verlangt, wird selten ganz erledigt, und was
    fehlt, faellt niemandem auf.
    """
    teile = re.split(r"\s*(?:;|\bund dann\b|\bdanach\b)\s*", str(wunsch))
    return [t.strip() for t in teile if len(t.strip()) >= MINDESTZEICHEN]


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def selbsttest():
    print("Selbsttest auftrag")
    gesamt = 0
    fehler = 0

    def pruefe(bedingung, was):
        nonlocal gesamt, fehler
        gesamt += 1
        print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
        if not bedingung:
            fehler += 1

    ja, grund = pruefen("Erstelle eine Liste der groessten Dateien unter "
                        "werkstatt und schreibe sie nach werkstatt/gross.txt")
    pruefe(ja, "guter Auftrag wird angenommen: %s" % grund)

    ja, grund = pruefen("Mach das nochmal fertig")
    pruefe(not ja and "nicht kennt" in grund,
           "Verweis auf das Gespräch wird abgelehnt: %s" % grund[:60])

    ja, grund = pruefen("Die Platte ist ziemlich voll geworden in letzter Zeit")
    pruefe(not ja and "was getan werden soll" in grund,
           "Beschreibung ohne Auftrag wird abgelehnt")

    ja, grund = pruefen("Mach mal")
    pruefe(not ja and "zu kurz" in grund, "zu kurz wird abgelehnt")

    sonde = pruefung_vorschlagen(
        "Schreibe die Liste nach werkstatt/gross.txt")
    pruefe(sonde["art"] == "datei_existiert" and "gross.txt" in sonde["pfad"],
           "Prüfung an einer Datei vorgeschlagen: %s" % sonde["pfad"])

    sonde = pruefung_vorschlagen("Denk mal über die Lage nach")
    pruefe(sonde["art"] == "keine",
           "ohne Spur ehrlich: %s" % sonde["text"][:60])

    teile = zerlegen("Erstelle den Ordner werkstatt/alt und dann verschiebe "
                     "alle alten Journale dorthin")
    pruefe(len(teile) == 2, "grober Wunsch in zwei Aufträge zerlegt: %d"
           % len(teile))

    teile = zerlegen("Schreibe eine Liste der Dateien nach werkstatt/liste.txt")
    pruefe(len(teile) == 1, "einfacher Wunsch bleibt einer")

    print("%d von %d bestanden" % (gesamt - fehler, gesamt))
    return 1 if fehler else 0


def main():
    p = argparse.ArgumentParser(description="Auftraege an Claude schaerfen.")
    p.add_argument("--pruefen", help="Taugt dieser Auftrag?")
    p.add_argument("--zerlegen", help="In Einzelaufträge zerlegen")
    p.add_argument("--selbsttest", action="store_true")
    a = p.parse_args()

    if a.selbsttest:
        return selbsttest()
    if a.zerlegen:
        for t in zerlegen(a.zerlegen):
            print("- %s" % t)
        return 0
    if a.pruefen:
        ja, grund = pruefen(a.pruefen)
        print("%s - %s" % ("taugt" if ja else "taugt nicht", grund))
        if ja:
            print("Prüfen danach: %s"
                  % pruefung_vorschlagen(a.pruefen)["text"])
        return 0 if ja else 2
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
