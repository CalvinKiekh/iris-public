"""Probe fuer kann.py - und, mit --echt, fuer die Antwort, die Calvin hoert.

    python kann_test.py          nur die Listen, kein Modell
    python kann_test.py --echt   dazu: die echten Fragen durch gespraech.py

Der Beleg, den der Mac sehen will: Calvin fragt "Was kannst du alles?" und
bekommt eine Antwort, die stimmt - mit dem, was geprueft ist, und dem, was
noch nie gebraucht wurde. Pruefbar gegen faehigkeiten.json. Genau das misst
--echt: jede Faehigkeit, die er nennt, wird gegen die Listen gehalten.

Es wird nichts geschrieben: kein Journal, keine Datei im Gespraechsordner,
keine Stimme. Nur gefragt und verglichen.
"""
from __future__ import annotations

from einstellungen import NAME
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pruefstand

import probenort
import kann

GESAMT = 0
FEHLER = 0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def probe_listen() -> None:
    print("\ndie Listen, aus einem Wegwerf-Verzeichnis")
    ort = probenort.ablage("kann")
    try:
        (ort / "werkzeuge.json").write_text(json.dumps([
            {"name": "stimme_hoeren", "zweck": "Misst Tonhöhe und Pausen",
             "geprueft": True, "ergebnis": "Tonhöhe erkannt: 149.5 Hz"},
            {"name": "netz", "zweck": "Sagt, wer im Heimnetz ist",
             "geprueft": True, "ergebnis": "14 Geräte gefunden"},
        ], ensure_ascii=False), encoding="utf-8")
        (ort / "faehigkeiten.json").write_text(json.dumps([
            {"name": "Von sich aus sprechen", "zweck": f"Spreche {NAME} an",
             "geprueft": False, "ergebnis": "Noch nie getan."},
        ], ensure_ascii=False), encoding="utf-8")

        k = kann.kurz(ort)
        pruefe(k["wie_viele"] == 3, "beide Listen zusammen (%d)" % k["wie_viele"])
        pruefe(k["noch_nie_benutzt"] == ["Von sich aus sprechen"],
               "was nie benutzt wurde, steht eigens da")
        pruefe(len(json.dumps(k, ensure_ascii=False)) < 1200,
               "kurz bleibt kurz - es geht in JEDE Antwort")

        a = kann.auskunft(ort, "Wie verarbeitest du meine Stimme?")
        mit = [e["name"] for e in a["geprueft"] if e.get("beleg")]
        pruefe(mit == ["stimme_hoeren"],
               "der Beleg geht dorthin, wo gefragt wurde (%s)" % mit)
        pruefe(all(e.get("warum_nicht") for e in a["noch_nie_benutzt"]),
               "das nie Benutzte traegt seinen Grund IMMER mit")
        pruefe(len(a["geprueft"]) == 2,
               "die anderen stehen trotzdem da, nur ohne Beleg")

        a2 = kann.auskunft(ort, "Was kannst du alles?")
        pruefe(not any(e.get("beleg") for e in a2["geprueft"]),
               "eine allgemeine Frage traegt keinen Beleg - "
               "\"alles\" und \"kannst\" treffen sonst jeden Eintrag")

        # Die Sprechform, gemessen vom Mac am 12.09.: fuenf genannte Sachen
        # ergaben 34 Woerter in vier Saetzen - ein Katalog, kein Satz.
        pruefe(a2["gezielt"] is False,
               "eine allgemeine Frage ist nicht gezielt")
        pruefe(len(a2["nenne_diese"]) <= kann.STOFF_ALLGEMEIN,
               "und nennt hoechstens %d Sachen, nicht fuenf (%d)"
               % (kann.STOFF_ALLGEMEIN, len(a2["nenne_diese"])))

        a3 = kann.auskunft(ort, "Wie verarbeitest du meine Stimme?")
        pruefe(a3["gezielt"] is True,
               "eine gezielte Frage ist gezielt - dann gehoeren die Treffer hin")

        b_allgemein = kann.block(ort, "Was kannst du?")
        b_gezielt = kann.block(ort, "Wie verarbeitest du meine Stimme?")
        pruefe("ZWEI ODER DREI Saetzen" in b_allgemein,
               "der allgemeine Block verlangt zwei bis drei Saetze")
        pruefe("KEIN Katalog" in b_allgemein,
               "und verbietet die Aufzaehlung ausdruecklich")
        # Umgedreht seit dem 12.09. 17:15: Erst verlangte die Anweisung die
        # Gesamtzahl als Nachsatz ("Satz 3: dass es insgesamt N sind"), und
        # genau die kam zurueck - "Es gibt insgesamt 27 Faehigkeiten". Der Mac:
        # "Eine Zahl ist keine Auskunft - niemand fragt wie viele, sondern
        # was." Jetzt wird sie ausdruecklich VERBOTEN.
        pruefe("NENNE KEINE ANZAHL" in b_allgemein,
               "die Anweisung verbietet jede Anzahl")
        pruefe("ZWEI ANDERE" in b_allgemein,
               "und verbietet, dieselbe Sache zweimal zu nennen")
        pruefe("Je EIN vollstaendiger deutscher Satz" in b_gezielt,
               "der gezielte Block bleibt bei einem Satz je Treffer")
        pruefe("ZWEI ODER DREI Saetzen" not in b_gezielt,
               "und verlangt keinen Wesenssatz - danach war nicht gefragt")

        t = kann.fuer_tick(ort)
        pruefe(t["werkzeuge_zum_aufrufen"][0].startswith("stimme_hoeren:"),
               "der Tick bekommt Name und Zwecksatz wie bisher")

        leer = probenort.ablage("kann_leer")
        pruefe(kann.kurz(leer)["wie_viele"] == 0
               and kann.auskunft(leer)["geprueft"] == [],
               "ohne Listen keine Ausnahme, nur nichts")
        probenort.wegraeumen(leer)
    finally:
        probenort.wegraeumen(ort)


def probe_fragen() -> None:
    print("\nwelche Frage die volle Auskunft holt")
    for f in ("Was kannst du alles?", "Was kannst du?",
              "Wie verarbeitest du meine Stimme?",
              "Welche Werkzeuge hast du?", "Wie funktioniert dein Gedächtnis?",
              "Hast du das schon mal benutzt?", "Woher weißt du das?",
              "Woher weisst du das?"):
        pruefe(kann.ist_faehigkeitsfrage(f), f"erkannt: {f}")
    for f in ("Wie spät ist es?", "Was hast du heute gemacht?",
              "Wie viel Platz ist frei?", "Wer ist im Netz?",
              "Gibt es etwas, das ich wissen sollte?"):
        pruefe(not kann.ist_faehigkeitsfrage(f),
               f"nicht erkannt, und das ist richtig: {f}")


def probe_echte_listen() -> None:
    print("\ndie echten Listen dieses Bewohners")
    k = kann.kurz()
    print(f"  {k['wie_viele']} Eintraege, davon noch nie benutzt: "
          f"{', '.join(k['noch_nie_benutzt']) or 'keiner'}")
    if pruefstand.bewohner_da():
        pruefe(k["wie_viele"] >= 20, "die Listen sind da")
    else:
        print("  --  die Listen: hier wohnt kein Bewohner")
    pruefe(len(json.dumps(k, ensure_ascii=False)) < 1000,
           "kurz ist %d Zeichen - vertretbar in jeder Antwort"
           % len(json.dumps(k, ensure_ascii=False)))
    a = kann.auskunft(frage="Wie verarbeitest du meine Stimme?")
    zeichen = len(json.dumps(a, ensure_ascii=False))
    print(f"  volle Auskunft: {zeichen} Zeichen")
    pruefe(zeichen < 5000, "und die volle Auskunft passt unter die Grenze")


# ----------------------------------------------------------- die echte Frage


FRAGEN = [
    "Was kannst du alles?",
    "Wie verarbeitest du meine Stimme?",
    "Gibt es etwas, das du kannst, aber noch nie gebraucht hast?",
]


def _namen_aller() -> list[str]:
    return [e["name"] for e in kann.eintraege()]


def _betriebsantwort(g, frage: str) -> str:
    """Die Antwort auf DEM Weg, den das Gespraech geht.

    Diese Probe fragte bis zum 12.09. ueber `_antwort_holen()` - und das ist
    ein anderer Aufruf als der im Betrieb: ohne Strom und ohne `think: "low"`.
    Gemessen am selben Prompt, dieselbe Frage:

        ohne think   4288 Zeichen Nachdenken, dann ein guter Satz
                     (und in zwei von drei Laeufen gar nichts, weil das
                      Modell im Nachdenken blieb)
        think=low     652 Zeichen Nachdenken, dann eine Namensliste

    Die Probe meldete also "bestanden" fuer eine Antwort, die Calvin nie zu
    hoeren bekommt. Derselbe Fehler wie bei den zwei Fehlalarmen vom
    Vormittag und beim nachgebauten Aufruf um 10:45: nicht das gemessen, was
    laeuft. `_antwort_stroemen()` ist, was laeuft.

    Geschrieben wird nichts: kein Journal, keine Datei, keine Stimme.
    """
    import threading
    nachrichten = g._antwort_holen(frage, {"state": "wach"},
                                   {"vorgaenge": []}, nur_bauen=True)
    saetze: list = []
    g._abbruch = threading.Event()
    g._antwort_stroemen(nachrichten, saetze, threading.Event())
    return " ".join(s.strip() for s in saetze).strip()


def echte_antworten() -> None:
    """Die Fragen durch gespraech.py, wie Calvin sie stellt."""
    from gespraech import Gespraech

    print("\n" + "=" * 70)
    print("Die echten Fragen - Antwort und Gegenprobe gegen die Listen")
    print("=" * 70)

    ort = probenort.ablage("kann_gespraech")
    # Die Werkstatt MUSS die echte sein - sonst pruefen wir eine erfundene
    # Faehigkeitsliste. Deshalb liegt der Gespraechsordner darin.
    echt = Path(__file__).parent / "werkstatt"
    probe_ordner = echt / "_kann_probe"
    probe_ordner.mkdir(exist_ok=True)
    try:
        g = Gespraech(probe_ordner, lambda *a, **k: None,
                      Path("nicht-vorhanden.wav"))
        alle = _namen_aller()
        nie = [e["name"] for e in kann.eintraege() if not e["geprueft"]]
        for frage in FRAGEN:
            print(f"\nFRAGE: {frage}")
            n = g._nachrichten(frage, {"state": "wach"}, {"vorgaenge": []})
            zeichen = sum(len(x.get("content", "")) for x in n)
            traegt = any("Was ich kann" in x.get("content", "") for x in n)
            print(f"  Prompt {zeichen} Zeichen, volle Auskunft dabei: {traegt}")
            antwort = _betriebsantwort(g, frage)
            print(f"  ANTWORT: {antwort}")
            pruefe(bool(antwort), "es kam ueberhaupt eine Antwort")
            # Die Frage, um die es Calvin geht. "Ich kann 27 Dinge" ist
            # technisch richtig und als Auskunft wertlos; eine Aufzaehlung
            # von Werkzeugnamen ebenso. Beides ist messbar: eine Antwort, die
            # fast nur aus Namen besteht, hat nichts erklaert.
            if "kannst du" in frage:
                namen_drin = sum(1 for x in alle if x.lower() in antwort.lower())
                woerter = len(antwort.split())
                pruefe(not re.search(r"kann\s+\d+\s+\w+e?\b", antwort)
                       and woerter >= 20 and namen_drin <= 8,
                       "eine Auskunft, keine Liste und keine Zahl "
                       "(%d Woerter, %d Namen): %s"
                       % (woerter, namen_drin, antwort[:60]))

            # Die Gegenprobe: Jeder Werkzeugname, den er nennt, muss in den
            # Listen stehen. Namen mit Unterstrich sind eindeutig genug, um
            # sie woertlich zu suchen - "stimme_hoeren" kann er nicht zufaellig
            # sagen.
            erfunden = [w for w in re.findall(r"\b[a-z]+_[a-z]+\b", antwort)
                        if w not in alle]
            pruefe(not erfunden,
                   "keine erfundenen Werkzeugnamen%s"
                   % (": " + ", ".join(erfunden) if erfunden else ""))
            genannt = [x for x in alle if x.lower() in antwort.lower()]
            print(f"  nennt aus den Listen: {', '.join(genannt) or '(keine)'}")
            if "nie gebraucht" in frage:
                pruefe(any(x in genannt for x in nie),
                       "auf die Frage nach dem Ungebrauchten nennt er eines "
                       "der zwei: %s" % ", ".join(nie))
    finally:
        probenort.wegraeumen(probe_ordner)
        probenort.wegraeumen(ort)


def main() -> int:
    print("Probe kann")
    probe_listen()
    probe_fragen()
    probe_echte_listen()
    if "--echt" in sys.argv:
        echte_antworten()
    print("\n%d von %d bestanden" % (GESAMT - FEHLER, GESAMT))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
