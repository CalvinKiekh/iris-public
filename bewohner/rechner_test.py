"""Probe fuer die Volkszaehlung des Rechners.

    python -X utf8 rechner_test.py

Gemessen wird ohne PowerShell und ohne Gedaechtnis: `lauf` und `merken` sind
Parameter, damit diese Probe nicht misst, was der Rechner heute gerade tut,
und nicht ins Echte schreibt. Dreimal ist an genau dieser Stelle schon eine
Probe ins Echte gelaufen.
"""
from __future__ import annotations

from einstellungen import NAME
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import probenort
import rechner

GESAMT = 0
FEHLER = 0
JETZT = 1789300000.0

MESSUNG = {
    "platten": [{"name": "C:", "frei_gb": 1534, "gross_gb": 3814}],
    "programme": {"anzahl": 121,
                  "namen": ["AMD Software", "ARC Raiders", "Bonjour",
                            "Corsair iCUE5", "Epic Games Launcher", "Steam",
                            "Tailscale", "Visual Studio Code"]},
    "dienste": {"insgesamt": 320, "laufen": 158,
                "namen": ["AMD Crash Defender", "DNS-Client", "Ollama",
                          "Tailscale", "Windows Update"]},
    "autostart": {"anzahl": 22, "namen": ["Discord", "OneDrive", "Steam"]},
    "ordner": [{"name": "Documents", "dateien": 5, "ordner": 20,
                "groesste": [".claude", "aimusic", "atlas"]},
               {"name": "Music", "dateien": 0, "ordner": 0, "groesste": []}],
}


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def probe_saetze() -> None:
    print("\nAus Zahlen werden Saetze - ohne Modell")
    s = rechner.saetze(MESSUNG)
    nach = {e["schluessel"]: e["satz"] for e in s}
    pruefe("rechner:platten" in nach, "ein Satz ueber die Platten")
    pruefe("1534" in nach.get("rechner:platten", ""),
           "mit der gemessenen Zahl: %s" % nach.get("rechner:platten"))
    pruefe("121" in nach.get("rechner:programme", ""),
           "die Zahl der Programme: %s" % nach.get("rechner:programme"))
    pruefe("320" in nach.get("rechner:dienste", "")
           and "158" in nach.get("rechner:dienste", ""),
           "eingerichtete UND laufende Dienste: %s" % nach.get("rechner:dienste"))
    pruefe("rechner:autostart" in nach, "was beim Start mitlaeuft")
    pruefe("rechner:ordner:documents" in nach, "und je Ordner einer")
    pruefe("rechner:ordner:music" not in nach,
           "ein leerer Ordner gibt keinen Satz - 0 Dateien, 0 Ordner ist "
           "keine Auskunft")

    # Keine Zahl darf entstehen, die nicht gemessen wurde.
    import re
    gemessen = {"1534", "3814", "121", "320", "158", "22", "5", "20"}
    erfunden = []
    for satz in nach.values():
        for zahl in re.findall(r"\d{2,}", satz):
            if zahl not in gemessen:
                erfunden.append((zahl, satz[:50]))
    pruefe(not erfunden, "keine erfundene Zahl: %s" % erfunden)


def probe_auswahl_quer() -> None:
    print("\nDie Namen werden quer durch die Liste gegriffen")
    lang = ["AMD %d" % i for i in range(30)] + ["Steam", "Tailscale"]
    gewaehlt = rechner._namen(lang)
    pruefe(gewaehlt.count("AMD") < 6,
           "nicht sechsmal derselbe Anfang: %s" % gewaehlt)
    pruefe("Steam" in gewaehlt or "Tailscale" in gewaehlt,
           "das Ende der Liste kommt vor: %s" % gewaehlt)
    kurz = rechner._namen(["eins", "zwei"])
    pruefe(kurz == "eins, zwei", "eine kurze Liste bleibt ganz: %s" % kurz)
    pruefe(rechner._namen([]) == "", "eine leere gibt nichts")
    pruefe(rechner._namen(None) == "", "und None auch nicht")


def probe_trockenlauf() -> None:
    print("\nEin Trockenlauf aendert den Zustand NICHT")
    ort = probenort.ablage("rechner")
    try:
        rechner.WERKSTATT = ort
        rechner.ZUSTAND = ort / "rechner.json"
        b = rechner.durchgang(jetzt=JETZT, lauf=lambda: MESSUNG)
        pruefe(b["gemessen"], "gemessen")
        pruefe(b["gemerkt"] == len(b["saetze"]),
               "er sagt, was er anlegen WUERDE: %d" % b["gemerkt"])
        pruefe(not rechner.ZUSTAND.exists(),
               "und schreibt keinen Zustand - sonst haelt der naechste "
               "echte Lauf alles fuer unveraendert und merkt NIE etwas")
    finally:
        probenort.wegraeumen(ort)


def probe_ueberholen() -> None:
    print("\nDer zweite Lauf ueberholt, statt danebenzulegen")
    ort = probenort.ablage("rechner")
    try:
        rechner.WERKSTATT = ort
        rechner.ZUSTAND = ort / "rechner.json"
        gemerkt, ersetzt = [], []

        def merken(art, text, quelle, alt=None):
            gemerkt.append((art, text, quelle, alt))
            return len(gemerkt)

        b1 = rechner.durchgang(jetzt=JETZT, lauf=lambda: MESSUNG, merken=merken)
        pruefe(b1["gemerkt"] == 5, "fuenf Saetze beim ersten Mal: %d" % b1["gemerkt"])
        pruefe(all(a == "zuhause" for a, _, _, _ in gemerkt),
               "alle als Art `zuhause` - dasselbe Fach wie sein uebriges "
               "Wissen ueber das Haus")
        pruefe(all(alt is None for _, _, _, alt in gemerkt),
               "beim ersten Mal wird nichts ersetzt")

        # Unveraendert: nichts Neues.
        vorher = len(gemerkt)
        b2 = rechner.durchgang(jetzt=JETZT + 60, lauf=lambda: MESSUNG, merken=merken)
        pruefe(b2["gemerkt"] == 0 and len(gemerkt) == vorher,
               "derselbe Rechner gibt nichts Neues: %d" % b2["gemerkt"])
        pruefe(b2["unveraendert"] == 5, "fuenf unveraendert: %d" % b2["unveraendert"])

        # Geaendert: der alte Satz wird ueberholt, nicht verdoppelt.
        anders = {**MESSUNG, "platten": [{"name": "C:", "frei_gb": 900,
                                          "gross_gb": 3814}]}
        b3 = rechner.durchgang(jetzt=JETZT + 120, lauf=lambda: anders, merken=merken)
        pruefe(b3["gemerkt"] == 1, "nur der geaenderte Satz: %d" % b3["gemerkt"])
        pruefe(gemerkt[-1][3] is not None,
               "und er ERSETZT den alten: ersetzt=%s" % (gemerkt[-1][3],))
        pruefe("900" in gemerkt[-1][1], "mit der neuen Zahl: %s" % gemerkt[-1][1])

        # Eine Gruppe, die es nicht mehr gibt, wird veraltet.
        ohne = {k: v for k, v in MESSUNG.items() if k != "autostart"}
        b4 = rechner.durchgang(jetzt=JETZT + 180, lauf=lambda: ohne,
                               merken=merken,
                               veralten=lambda k: ersetzt.append(k))
        pruefe("rechner:autostart" in b4["veraltet"],
               "die verschwundene Gruppe wird veraltet: %s" % b4["veraltet"])
        pruefe(ersetzt, "und ihre Erinnerung bekommt die Marke: %s" % ersetzt)
    finally:
        probenort.wegraeumen(ort)


def probe_keine_messung() -> None:
    print("\nOhne Messung wird nichts behauptet")
    ort = probenort.ablage("rechner")
    try:
        rechner.WERKSTATT = ort
        rechner.ZUSTAND = ort / "rechner.json"
        zeilen = []
        b = rechner.durchgang(jetzt=JETZT, lauf=lambda: None,
                              merken=lambda *a: 1,
                              journal=lambda k, t, **e: zeilen.append((k, t)))
        pruefe(not b["gemessen"], "er sagt, dass er nicht gemessen hat")
        pruefe(b["gemerkt"] == 0, "und merkt nichts")
        pruefe(any(k == "fehler" for k, _ in zeilen),
               "es steht als Fehler im Journal: %s" % zeilen)
    finally:
        probenort.wegraeumen(ort)


def probe_faellig() -> None:
    print("\nViermal am Tag, nicht im Minutentakt")
    pruefe(rechner.STUNDEN >= 1.0,
           "der Abstand ist Stunden, nicht Minuten: %s" % rechner.STUNDEN)
    ort = probenort.ablage("rechner")
    try:
        rechner.WERKSTATT = ort
        rechner.ZUSTAND = ort / "rechner.json"
        pruefe(rechner.faellig(JETZT), "ohne Zustand ist es faellig")
        rechner._zustand_schreiben({"zuletzt": JETZT})
        pruefe(not rechner.faellig(JETZT + 60), "gerade gelaufen: nicht faellig")
        pruefe(rechner.faellig(JETZT + rechner.STUNDEN * 3600 + 1),
               "nach der Frist wieder")
    finally:
        probenort.wegraeumen(ort)


def probe_eine_quelle() -> None:
    print("\nDie Ordnerliste steht nur an EINER Stelle")
    befehl = rechner._befehl()
    for name in rechner.PROFIL_ORDNER:
        pruefe("'%s'" % name in befehl, "%s steht im Befehl" % name)
    pruefe("AppData" not in befehl,
           f"AppData nicht - dort liegt nichts, was {NAME} je gesucht hat")
    pruefe("%(ordner)s" not in befehl, "und die Stelle ist wirklich gefuellt")


def main() -> int:
    probe_saetze()
    probe_auswahl_quer()
    probe_trockenlauf()
    probe_ueberholen()
    probe_keine_messung()
    probe_faellig()
    probe_eine_quelle()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
