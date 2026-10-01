"""Bekommt "Wer bist du?" eine Person - oder eine Taetigkeitsliste?

Der Mangel, gemessen vom Mac am 12.09. um 16:47:

    F: Wer bist du eigentlich?
    A: Ich bin ein Computer, der Geraete im Heimnetz erkennt, Daten
       ueberwacht, Code prueft und Erinnerungen speichert.

Zwei Fehler in einem Satz. "Ich bin ein Computer" ist falsch - er WOHNT auf
dem Rechner, er IST ihn nicht. Und der Rest ist wieder eine Taetigkeitsliste,
nur in einen Relativsatz gepackt.

Die Ursache war kein Modellfehler: werkstatt/ICH.md wurde seit dem 11.09.
taeglich geschrieben und NIE GELESEN. Der Name, den er sich selbst gegeben
hat, stand in einer Datei, die niemand in den Prompt gelegt hat - obwohl der
Kommentar ueber SYSTEM behauptete, "wer er ist, kommt aus ICH.md".

    python -X utf8 ich_gespraech_test.py          nur die Logik
    python -X utf8 ich_gespraech_test.py --echt   dazu die echte Frage
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pruefstand

import gespraech
import ich

HIER = Path(__file__).resolve().parent
GESAMT = 0
FEHLER = 0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def probe_erkennung() -> None:
    print("\nwelche Frage nach IHM fragt, nicht nach seinen Faehigkeiten")
    for f in ("Wer bist du eigentlich?", "Wer bist du?", "Was bist du?",
              "Wie heißt du?", "Wie ist dein Name?", "Hast du einen Namen?",
              "Stell dich mal vor", "Erzähl mal von dir",
              "Sag mal, wer du bist"):
        pruefe(gespraech.IDENTITAETSFRAGE.search(f), "erkannt: %r" % f)

    # Die Faehigkeitsfrage darf NICHT als Identitaetsfrage gelten und
    # umgekehrt - sonst tauschen wir einen Mangel gegen den anderen.
    import kann
    for f in ("Was kannst du?", "Was kannst du alles?",
              "Welche Werkzeuge hast du?"):
        pruefe(not gespraech.IDENTITAETSFRAGE.search(f),
               "keine Identitaetsfrage: %r" % f)
    for f in ("Wer bist du?", "Wie heißt du?"):
        pruefe(not kann.ist_faehigkeitsfrage(f),
               "und keine Faehigkeitsfrage: %r" % f)

    for f in ("Wie spät ist es?", "Wer ist im Heimnetz?",
              "Wie heißt meine Tochter?"):
        pruefe(not gespraech.IDENTITAETSFRAGE.search(f),
               "gar nichts davon: %r" % f)


def probe_name_lesen() -> None:
    print("\nder Name wird aus ICH.md gelesen")
    beispiel = ("# Ich\n\nZuletzt fortgeschrieben am 12.09.2026 09:25.\n\n"
                "## Name\n\nLlamaWerkstatt  \nIch habe sieben Llama-"
                "Serverprozesse verwaltet und Werkzeuge selbst gebaut.\n\n"
                "## Wer ich bin\n\nIch habe 54 Mal nachgesehen, ohne etwas "
                "zu tun.\n")
    n = ich.abschnitt("Name", beispiel)
    pruefe(n.startswith("LlamaWerkstatt"), "der Abschnitt Name: %r" % n[:40])
    w = ich.abschnitt("Wer ich bin", beispiel)
    pruefe("54 Mal" in w, "und der Abschnitt Wer ich bin getrennt davon")
    pruefe("LlamaWerkstatt" not in w,
           "die Abschnitte laufen nicht ineinander")

    # Ohne Datei keine Behauptung.
    leer = ich.abschnitt("Name", "# Ich\n\nnichts weiter\n")
    pruefe(leer == "", "ohne Abschnitt nichts: %r" % leer)


def probe_block() -> None:
    print("\nwas im Prompt steht, wenn nach ihm gefragt wird")
    b = gespraech.ich_block(HIER / "werkstatt")
    print("      %s" % b.replace("\n", "\n      ")[:700])

    pruefe("[Wer ich bin]" in b, "ein eigener Block")
    pruefe("NICHT DIESER RECHNER" in b,
           "die Verwechslung wird ausdruecklich verboten")
    pruefe("Ich bin ein Computer" in b,
           "und zwar mit dem echten Fehlsatz als Beispiel")
    pruefe("KEINE Liste deiner" in b,
           "die Faehigkeitsliste wird ausgeschlossen")
    pruefe("ZWEI ODER DREI" in b, "zwei bis drei Saetze verlangt")

    # Der Name, wenn es einen gibt - und kein erfundener, wenn nicht.
    name, _ = ich.name_und_grund()
    if name:
        pruefe(name in b, "der eigene Name steht drin: %s" % name)
        pruefe("SELBST gegeben" in b,
               "und als selbstgewaehlt gekennzeichnet")
    else:
        pruefe("noch keinen Namen" in b,
               "ohne Namen wird keiner erfunden")

    # Wohnort und seit wann - gemessen, nicht behauptet.
    if pruefstand.bewohner_da():
        seit = gespraech._wohnt_seit(HIER / "werkstatt")
        pruefe(seit and seit in b, "seit wann er wach ist, aus dem Journal: %s" % seit)
    else:
        print("  --  seit wann er wach ist: kein Journal, hier wohnt kein Bewohner")

    # Ohne Werkstatt kein Absturz und keine erfundene Auskunft.
    leer = Path(tempfile.mkdtemp(prefix="ich_leer_"))
    b2 = gespraech.ich_block(leer)
    pruefe("[Wer ich bin]" in b2, "ohne Werkstatt kommt trotzdem ein Block")
    pruefe(gespraech._wohnt_seit(leer) == "",
           "aber kein erfundenes Datum")


def probe_verdraengt_die_liste() -> None:
    """Der Kern: Bei einer Frage nach ihm darf die Faehigkeitsliste NICHT
    daneben stehen. Stuenden beide da, gewaenne die Liste - sie ist
    konkreter."""
    print("\ndie Faehigkeitsliste wird verdraengt, nicht ergaenzt")
    import kann
    frage = "Wer bist du eigentlich?"
    pruefe(not kann.ist_faehigkeitsfrage(frage),
           "kann.block() wird fuer diese Frage gar nicht geholt")
    b = gespraech.ich_block(HIER / "werkstatt")
    pruefe("GRUPPE A" not in b and "Werkzeuge zum Aufrufen" not in b,
           "und im Identitaetsblock steht keine Werkzeugliste")


def echt() -> None:
    print("\n" + "=" * 66)
    print("Die echte Frage, auf dem Betriebsweg")
    print("=" * 66)
    import threading
    from gespraech import Gespraech
    probe = HIER / "werkstatt" / "_ich_probe"
    probe.mkdir(exist_ok=True)
    for frage in ("Wer bist du eigentlich?", "Wie heißt du?"):
        g = Gespraech(probe, lambda *a, **k: None, Path("nicht-da.wav"))
        n = g._antwort_holen(frage, {"state": "wach"}, {"vorgaenge": []},
                             nur_bauen=True)
        saetze: list = []
        g._abbruch = threading.Event()
        g._antwort_stroemen(n, saetze, threading.Event())
        a = " ".join(s.strip() for s in saetze).strip()
        print("\n  F: %s" % frage)
        print("  A: %s" % a)
        pruefe(len(a) > 15, "es kam eine Antwort")
        pruefe("ich bin ein computer" not in a.lower(),
               "und nicht \"Ich bin ein Computer\"")
        name, _ = ich.name_und_grund()
        if name:
            pruefe(name.lower() in a.lower(),
                   "der eigene Name kommt vor (%s)" % name)


if __name__ == "__main__":
    print("Probe Identitaetsfrage")
    probe_erkennung()
    probe_name_lesen()
    probe_block()
    probe_verdraengt_die_liste()
    if "--echt" in sys.argv:
        echt()
    print("\n%d von %d bestanden" % (GESAMT - FEHLER, GESAMT))
    raise SystemExit(1 if FEHLER else 0)
