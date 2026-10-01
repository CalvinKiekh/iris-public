"""Probe fuer wissen.py.

    python wissen_test.py          nur die Logik, kein Modell
    python wissen_test.py --echt   dazu: gpt-oss zieht aus einem echten
                                   Gespraechsverlauf

Es wird NICHTS ins Gedaechtnis geschrieben - `merken` und `journal` sind
Parameter, und die Probe reicht Attrappen hinein. An genau dieser Stelle sind
am 12.09. schon zweimal Proben ins Echte gelaufen.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS
import sys
import time

import wissen

GESAMT = 0
FEHLER = 0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def paar(frage, antwort, vor_minuten=0.0):
    return {"frage": frage, "antwort": antwort,
            "ts": time.time() - vor_minuten * 60}


# Echte Zeilen aus werkstatt/gedaechtnis.db vom 12.09.
ECHT = [
    paar("Wie viel Arbeitsspeicher ist frei?",
         "Von 61.6 GB Arbeitsspeicher sind 38.6 GB frei.", 30),
    paar("Wie spät ist es?", "Es ist 13 Uhr.", 29),
    paar("Schnurpsel wrgl bitte?",
         "Entschuldigung, aber ich verstehe die Frage nicht.", 28),
    paar("Wie heißt meine Tochter?", "Lena Marie.", 27),
    paar("Wer belegt den meisten Speicher?",
         "Memory Compression mit 1533 MB.", 26),
]


def probe_lohnt() -> None:
    print("\nwelche Paare ueberhaupt Wissen tragen koennen")
    pruefe(not wissen.lohnt(ECHT[0]),
           "ein Messwert nicht - er ist morgen falsch")
    pruefe(not wissen.lohnt(ECHT[1]), "eine Uhrzeit nicht")
    pruefe(not wissen.lohnt(ECHT[2]), "eine Probe nicht")
    pruefe(wissen.lohnt(ECHT[3]), "die Tochter schon")
    pruefe(not wissen.lohnt(ECHT[4]), "wer gerade Speicher belegt, nicht")
    pruefe(wissen.lohnt(paar("Ich fahre morgen nach Hamburg.", "Notiert.")),
           f"und eine Mitteilung von {NAME} schon")
    pruefe(not wissen.lohnt(paar("Hi", "Hallo")),
           "zu kurz, um etwas zu enthalten")


def probe_lohnt_luecken() -> None:
    """Die fuenf Luecken, die am 12.09. am Gedaechtnis nachgezaehlt wurden.

    Jede steht hier mit der Anzahl, die deswegen im Gedaechtnis lag. Das ist
    der Grund, aus dem die Faelle einzeln dastehen und nicht als eine Zeile
    "erkennt vergaengliche Fragen": Faellt eine wieder aus, soll die Probe
    sagen, WELCHE.
    """
    print("\ndie fuenf gemessenen Luecken - jede mit ihrer Anzahl")
    weg = [
        ("Wie geht’s dir?", "typografischer Apostroph (1x im Gedaechtnis)"),
        ("Wie geht's dir?", "gerader Apostroph - ging vorher schon"),
        ("Wer ist im Heimnetz?", "Heimnetz, nicht nur Netz (2x)"),
        ("Wer ist im Netzwerk?", "Netzwerk ebenso"),
        ("Wer ist im Netz?", "das kannte es schon"),
        ("Wie ist dein Status", "gar kein Muster dafuer (1x), auch ohne ?"),
        ("Wie ist dein Status?", "mit Fragezeichen"),
        ("Was ist letzte Nacht passiert?", "Chronikfrage (8x!)"),
        ("Was war heute Nacht los?", "Chronik, andere Worte"),
        ("Was kannst du?", "Faehigkeitsfrage (4x!)"),
        ("Was kannst du alles?", "Faehigkeit, laengere Form (1x)"),
        ("Welche Werkzeuge hast du?", "Faehigkeit ueber die Werkzeuge"),
        ("Was hast du alles gemacht?", "seine eigene Arbeit (1x)"),
        # Am 12.09. um 16:47 durch die erste Fassung geschluepft, weil die
        # Fuellung zwischen "du" und "gemacht" aus einer Wortliste kam.
        # Liegt als Protokoll 117 im Gedaechtnis.
        ("Was hast du in der letzten Stunde gemacht?",
         "beliebige Fuellung dazwischen (1x, Protokoll 117)"),
        ("Was hast du heute so getan?", "getan statt gemacht"),
        ("Was hast du seit dem Neustart erledigt?", "erledigt, mit Fuellung"),
    ]
    for frage, warum in weg:
        pruefe(not wissen.lohnt(paar(frage, "Eine laengere Antwort darauf.")),
               "fliegt raus - %s: %r" % (warum, frage))

    # Die Gegenprobe. Eine Sperre, die zu viel faengt, ist schlimmer als die
    # Luecke: Dann verliert er die Tochter statt eines Messwerts.
    print("\n  und was trotzdem durchkommen MUSS")
    bleibt = [
        ("Merk dir mal, dass meine Tochter Lena Marie heißt.",
         "eine Mitteilung, die bleiben soll"),
        ("Wie heißt meine Tochter?", "eine Frage nach einem echten Fakt"),
        ("Ich muss morgen mit Lena zum Kinderarzt.", f"{NAMENS} Prüfstein aus C"),
        ("Meine Verlobte heißt Sara.", "die zweite Person"),
        ("Kannst du dir merken, dass ich keine Push nach 22 Uhr mag?",
         "eine Vorliebe - 'kannst du' ist hier keine Faehigkeitsfrage"),
    ]
    for frage, warum in bleibt:
        pruefe(wissen.lohnt(paar(frage, "Verstanden, ich merke es mir.")),
               "kommt durch - %s: %r" % (warum, frage))


def probe_episode() -> None:
    print("\nein Gespraech ist zu Ende, wenn Ruhe ist")
    jetzt = time.time()
    laufend = [paar("Was machst du?", "Ich sehe nach.", 1)]
    pruefe(wissen.episode(laufend, jetzt) == [],
           f"waehrend {NAME} noch redet, wird nichts ausgewertet")
    fertig = [paar("Meine Tochter heißt Lena.", "Gemerkt.", 20)]
    pruefe(len(wissen.episode(fertig, jetzt)) == 1,
           "nach der Ruhe schon")
    pruefe(wissen.episode([], jetzt) == [], "ohne Paare nichts")
    pruefe(wissen.episode([{"frage": "x", "antwort": "y"}], jetzt) == [],
           "ohne Zeitstempel auch nichts - dann weiss niemand, ob Ruhe ist")
    viele = [paar("f%d" % i, "a%d" % i, 20) for i in range(30)]
    pruefe(len(wissen.episode(viele, jetzt)) == wissen.PAARE_HOECHSTENS,
           "ein sehr langes Gespraech wird hinten gekappt")


def probe_wache() -> None:
    print("\ndie Wache: ein falscher Fakt bleibt und wird Wahrheit")
    quelle = (f"{NAME}: Wie heißt meine Tochter?\nDu: Lena Marie.\n"
              f"{NAME}: Ich fahre am 14. nach Hamburg.\nDu: Gemerkt.")
    gut = [f"{NAMENS} Tochter heißt Lena Marie.",
           f"{NAME} fährt am 14. nach Hamburg."]
    for s in gut:
        pruefe(wissen.mangel(s, quelle) is None, "darf hinein: %s" % s)

    schlecht = [
        ("Ich kann den Bildschirm beschreiben.", "ueber sich selbst"),
        (f"{NAME} fragte nach dem Arbeitsspeicher.", "nacherzaehlt"),
        (f"{NAME} fährt am 27. nach Hamburg.", "erfundene Zahl"),
        ("Lena.", "zu kurz"),
        (f"{NAME} " + "sehr " * 60 + "beschäftigt.", "zu lang"),
    ]
    for s, was in schlecht:
        m = wissen.mangel(s, quelle)
        pruefe(m is not None, "zurueckgehalten (%s): %s" % (was, m or "..."))


def probe_ganzer_weg() -> None:
    """Die Kette mit Attrappen - ohne Modell, ohne Gedaechtnis."""
    print("\nder ganze Weg, ohne etwas zu schreiben")
    gemerkt, notiert = [], []

    def falsches_modell(nachrichten):
        # Zwei brauchbare Fakten, zwei, die die Wache fangen muss.
        return {"fakten": [f"{NAMENS} Tochter heißt Lena Marie.",
                           "Ich kann den Speicher messen.",
                           f"{NAME} war 99 Mal in Hamburg.",
                           f"{NAME} arbeitet an der Brücke zum Mac."]}

    n = wissen.aus_gespraech(
        ECHT + [paar("Ich arbeite an der Brücke zum Mac.", "Verstanden.", 25)],
        time.time(),
        merken=lambda t: (gemerkt.append(t), 1)[1],
        journal=lambda art, text, **k: notiert.append(text),
        fragen=falsches_modell)
    pruefe(n == 2, "zwei von vier Fakten gemerkt, nicht vier (%d)" % n)
    pruefe(any("Lena Marie" in g for g in gemerkt), "die Tochter ist dabei")
    pruefe(any("Brücke" in g for g in gemerkt), "die Arbeit auch")
    pruefe(not any("Ich kann" in g for g in gemerkt),
           "die Selbstauskunft nicht: %s" % gemerkt)
    pruefe(not any("99" in g for g in gemerkt),
           "die erfundene Zahl nicht: %s" % gemerkt)
    pruefe(sum(1 for t in notiert if "zurueckgehalten" in t) == 2,
           "und beide Ablehnungen stehen mit Grund im Journal: %s" % notiert)

    # Ein laufendes Gespraech wird nicht angefasst.
    gemerkt.clear()
    n = wissen.aus_gespraech([paar("Meine Tochter heißt Lena.", "Gut.", 0.5)],
                             time.time(),
                             merken=lambda t: (gemerkt.append(t), 1)[1],
                             fragen=falsches_modell)
    pruefe(n == 0 and not gemerkt,
           "waehrend das Gespraech laeuft, wird nichts gemerkt")

    # Nur Messwerte: gar kein Modellaufruf.
    gefragt = []
    wissen.aus_gespraech(ECHT[:3], time.time(),
                         merken=lambda t: 1,
                         fragen=lambda n: gefragt.append(n) or {"fakten": []})
    pruefe(not gefragt,
           "aus lauter Messwerten wird das Modell gar nicht erst gefragt")


def echt() -> None:
    print("\n" + "=" * 66)
    print("gpt-oss an einem echten Verlauf")
    print("=" * 66)
    paare = ECHT + [
        paar("Ich arbeite am Wochenende an der Brücke zum Mac.",
             "Verstanden, ich merke es mir.", 25),
        paar("Meine Tochter Lena Marie kommt nächste Woche zu Besuch.",
             "Schön, ich habe es notiert.", 24),
    ]
    fakten, zurueck = wissen.auszug(paare)
    print("\nFakten:")
    for s in fakten or ["  (keine)"]:
        print("  + %s" % s)
    for s in zurueck:
        print("  - %s" % s)
    pruefe(any("Lena" in s for s in fakten),
           "die Tochter kommt durch")
    pruefe(not any(re.search(r"\d+[.,]?\d*\s*GB", s) for s in fakten),
           "kein Messwert als Fakt: %s" % fakten)


if __name__ == "__main__":
    import re
    print("Probe wissen")
    probe_lohnt()
    probe_lohnt_luecken()
    probe_episode()
    probe_wache()
    probe_ganzer_weg()
    if "--echt" in sys.argv:
        echt()
    print("\n%d von %d bestanden" % (GESAMT - FEHLER, GESAMT))
    raise SystemExit(1 if FEHLER else 0)
