"""Probe fuer E - Kurzzeit aus der Sitzung, Langzeit mit getrennten Faechern.

    python -X utf8 kurzzeit_test.py

Der Unterschied zu vorher ist ein Neustart: `self.verlauf` liegt im
Arbeitsspeicher und ist danach leer - "und davor?" verstand er nicht mehr. Die
Sitzung liegt auf der Platte und ueberlebt. Genau das wird hier gemessen, und
zwar indem der Verlauf ABSICHTLICH geleert wird.

Alles gegen ein FESTES Jetzt: Samstag, 12.09.2026, 14:00.
"""
from __future__ import annotations

from einstellungen import NUTZER
import sys
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
import gedaechtnis
import probenort
import sitzung

GESAMT = 0
FEHLER = 0
JETZT = datetime(2026, 9, 12, 14, 0).timestamp()
MIN = 60.0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


class Stummes:
    """Ein Gespraech ohne Bruecke, Stimme und Modell - nur der Prompt zaehlt."""

    def __init__(self):
        from gespraech import Gespraech
        self.g = Gespraech.__new__(Gespraech)
        self.g.verlauf = []
        self.g.journal = lambda *a, **k: None
        self.g._wissen_bis = 0.0

    def kurzzeit(self, sid):
        return self.g._kurzzeit(sid)


def frisch() -> Path:
    ordner = probenort.ablage("kurzzeit")
    sitzung.WERKSTATT = ordner
    sitzung.KOEPFE = ordner / "sitzungen.jsonl"
    sitzung.ORDNER = ordner / "sitzungen"
    return ordner


def probe_aus_der_sitzung() -> None:
    print("\nDer Kurzzeitkontext kommt aus der Sitzung")
    ordner = frisch()
    try:
        s = Stummes()
        sid = sitzung.sitzung_fuer(JETZT, NUTZER)
        sitzung.paar_anhaengen(sid, "Wer belegt den meisten Speicher?",
                               "llama-server mit 1,2 GB.", JETZT)
        sitzung.paar_anhaengen(sid, "Und wie viel ist frei?",
                               "Auf C sind 1537 GB frei.", JETZT + 60)

        n = s.kurzzeit(sid)
        pruefe(len(n) == 4, "zwei Paare werden vier Nachrichten: %d" % len(n))
        pruefe(n[0]["role"] == "user"
               and n[0]["content"].startswith("Wer belegt"),
               "in der Reihenfolge der Zeit: %s" % n[0]["content"][:40])
        pruefe(n[1]["role"] == "assistant" and "llama-server" in n[1]["content"],
               "Frage und Antwort abwechselnd")

        print("\nund er UEBERLEBT EINEN NEUSTART - darum geht es")
        pruefe(s.g.verlauf == [],
               "der Verlauf im Arbeitsspeicher ist leer, wie nach einem Start")
        n = s.kurzzeit(sid)
        pruefe(len(n) == 4,
               "und trotzdem stehen die zwei Paare da: %d Nachrichten" % len(n))
        pruefe(any("1537" in x["content"] for x in n),
               "woertlich, mit der Zahl von vorhin")
        # Der Gegenbeweis: ohne Sitzung bleibt nur der leere Verlauf.
        pruefe(s.kurzzeit(None) == [],
               "ohne Sitzung und ohne Verlauf: nichts - so war es vorher immer")

        print("\nnur die letzten PAARE_KONTEXT, nicht die ganze Sitzung")
        for i in range(8):
            sitzung.paar_anhaengen(sid, "Frage %d" % i, "Antwort %d" % i,
                                   JETZT + 120 + i)
        n = s.kurzzeit(sid)
        pruefe(len(n) == 2 * s.g.PAARE_KONTEXT,
               "zehn Paare, aber nur %d Nachrichten: %d"
               % (2 * s.g.PAARE_KONTEXT, len(n)))
        pruefe("Frage 7" in n[-2]["content"],
               "und zwar die LETZTEN: %s" % n[-2]["content"])
    finally:
        probenort.wegraeumen(ordner)


def probe_vorgaengerin() -> None:
    print("\nB4: die Zusammenfassung der Vorgaengerin geht voran")
    ordner = frisch()
    try:
        s = Stummes()
        alt = sitzung.sitzung_fuer(JETZT, NUTZER)
        sitzung.paar_anhaengen(alt, "Wie war das mit dem Kinderarzt?",
                               "Am Montag um zehn.", JETZT)
        sitzung.schliessen(alt, JETZT + 11 * MIN)
        sitzung.marke_setzen(alt, "zusammenfassung",
                             "Es ging um Lenas Termin beim Kinderarzt.")

        # Zwanzig Minuten spaeter: eine neue Sitzung, die auf die alte verweist.
        neu = sitzung.sitzung_fuer(JETZT + 20 * MIN, NUTZER)
        sitzung.paar_anhaengen(neu, "Und die Unterlagen?",
                               "Die Versichertenkarte reicht.",
                               JETZT + 20 * MIN)
        pruefe(sitzung.kopf(neu)["fortsetzung_von"] == alt,
               "die neue verweist auf die alte: %s"
               % sitzung.kopf(neu)["fortsetzung_von"])

        n = s.kurzzeit(neu)
        pruefe(n and n[0]["role"] == "system"
               and "Kinderarzt" in n[0]["content"],
               "und ihre Zusammenfassung steht vorn: %s"
               % (n[0]["content"][:58] if n else None))
        pruefe(any("Versichertenkarte" in x["content"] for x in n),
               "danach der eigene Wortlaut")

        # Ohne Zusammenfassung bei der Vorgaengerin: kein leerer Satz.
        ohne = sitzung.sitzung_fuer(JETZT + 60 * MIN, "handy")
        sitzung.paar_anhaengen(ohne, "Frage", "Antwort", JETZT + 60 * MIN)
        n = s.kurzzeit(ohne)
        pruefe(all(x["role"] != "system" for x in n),
               "ohne Vorgaengerin kein Systemsatz: %s" % [x["role"] for x in n])
    finally:
        probenort.wegraeumen(ordner)


def probe_ansprache_ohne_frage() -> None:
    print("\nEine Ansprache hat keine Frage (B9) - und kein leeres user-Wort")
    ordner = frisch()
    try:
        s = Stummes()
        sid = sitzung.sitzung_fuer(JETZT, NUTZER)
        sitzung.paar_anhaengen(sid, None, "Die Bruecke zum Mac ist wieder da.",
                               JETZT)
        n = s.kurzzeit(sid)
        pruefe(len(n) == 1 and n[0]["role"] == "assistant",
               "nur die Antwort, keine leere Frage: %s"
               % [(x["role"], x["content"][:28]) for x in n])
        pruefe(all(x["content"] for x in n), "und kein leerer Inhalt")
    finally:
        probenort.wegraeumen(ordner)


def probe_faecher() -> None:
    print("\nB3: getrennte Faecher statt eines gemeinsamen Deckels")
    pruefe(len(gedaechtnis.KONTINGENTE) >= 3,
           "es gibt Kontingente je Gruppe: %d" % len(gedaechtnis.KONTINGENTE))
    namen = [t for t, _, _ in gedaechtnis.KONTINGENTE]
    pruefe("Fakten" in namen, "ein Fach fuer Fakten: %s" % namen)

    import inspect
    sig = inspect.signature(gedaechtnis.abrufen)
    pruefe("arten" in sig.parameters,
           "abrufen() hat einen Artfilter: %s" % list(sig.parameters))
    sig = inspect.signature(gedaechtnis.fuer_prompt)
    pruefe("kontingente" in sig.parameters,
           "und fuer_prompt() nimmt die Kontingente als Parameter - damit die "
           "Messung aus E.4 sie umstellen kann")

    # Gefiltert wird IN der Suche: sonst waeren die besten Plaetze schon an
    # Arten vergeben, die nicht gefragt waren.
    quelle = Path(gedaechtnis.__file__).read_text(encoding="utf-8")
    pruefe("_fts_suche(v, frage, n * 3, arten, von)" in quelle
           and "_vektor_suche(v, frage, n * 3, arten, von)" in quelle,
           "beide Suchen bekommen die Filter, nicht nur eine")

    if gedaechtnis.DATENBANK.exists():
        treffer = gedaechtnis.abrufen("Welche Art Spiele habe ich?", 6,
                                      arten=("fakt",))
        pruefe(all(t["art"] == "fakt" for t in treffer),
               "am echten Gedaechtnis: nur Fakten kommen zurueck: %s"
               % [t["art"] for t in treffer])
        block = gedaechtnis.fuer_prompt("Welche Art Spiele habe ich?")
        pruefe("[Fakten]" in block,
               "und der Block ist beschriftet: %s"
               % [z for z in block.splitlines() if z.startswith("[")])


def probe_ueberholt_bleibt_findbar() -> None:
    """Ein ueberholter Satz bleibt ueber den Wortlaut seiner Vorfassungen
    findbar - sonst kuerzt das Ueberholen die Auskunft aus dem Gedaechtnis.

    Gemessen am 13.09. am echten Bestand: die Kette endete bei "Horror und
    Shooter; acht Verknuepfungen liegen auf dem Desktop." Das ist die beste
    Fassung und das Wort "Spiel" steht nicht mehr darin. Der Vektor fand sie,
    der Volltext nicht - und als der Einbetter einmal ausfiel, fand sie
    NIEMAND: die Antwort war "Ich kann dir die Art von Spielen nicht
    benennen", obwohl der Satz im Gedaechtnis stand. Darum wird hier mit
    ABGESCHALTETEM Einbetter geprueft; mit ihm ist die Luecke unsichtbar.
    """
    import sqlite3
    import tempfile

    print("\nEin ueberholter Satz bleibt findbar - ohne Einbetter")
    echt_db, echt_ws = gedaechtnis.DATENBANK, gedaechtnis.WERKSTATT
    echt_einbetten = gedaechtnis.einbetten
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as ordner:
        ort = Path(ordner)
        gedaechtnis.WERKSTATT, gedaechtnis.DATENBANK = ort, ort / "g.db"
        # Der Einbetter ist WEG. Nur der Volltext arbeitet.
        gedaechtnis.einbetten = lambda texte: None
        try:
            gedaechtnis.anlegen()
            with gedaechtnis._verbindung() as v:
                # Die Kette vom 13.09., nachgebaut. Die MITTLERE Fassung
                # traegt das Wort "Spiele" - der Volltext sucht Wortmarken,
                # nicht Anfaenge, und "Spielstarter" ist fuer ihn kein
                # Treffer auf "Spiele". Genau diese eine Fassung ist der
                # Handgriff, an dem die gueltige noch haengt.
                for text in ("Auf dem Desktop liegen acht Dateien, die "
                             "vorwiegend Horror- und Shooter-Spiele starten.",
                             "Spiele auf dem Desktop: Horror und Shooter.",
                             "Horror und Shooter; acht Verknuepfungen."):
                    v.execute("INSERT INTO erinnerung(ts, art, text, quelle, "
                              "wichtig) VALUES (?,?,?,?,0)",
                              (JETZT, "zuhause", text, "probe"))
                v.execute("UPDATE erinnerung SET ersetzt_durch=2 WHERE id=1")
                v.execute("UPDATE erinnerung SET ersetzt_durch=3 WHERE id=2")

            frage = "Welche Art Spiele habe ich?"
            treffer = gedaechtnis.abrufen(frage, 6, arten=("zuhause",))
            kennungen = [t["id"] for t in treffer]
            pruefe(3 in kennungen,
                   "die gueltige Fassung wird gefunden, obwohl 'Spiel' "
                   "nicht mehr darin steht: %s" % kennungen)
            pruefe(1 not in kennungen and 2 not in kennungen,
                   "und die ueberholten Fassungen kommen NICHT mit: %s"
                   % kennungen)
            pruefe(len(kennungen) == len(set(kennungen)),
                   "drei Fassungen einer Kette sind EIN Treffer, nicht drei")

            # Der Kopf zaehlt, nicht die Fassung: Fragt jemand nach einer
            # anderen Art, darf die Kette nicht ueber eine alte Fassung
            # hereinkommen.
            pruefe(gedaechtnis.abrufen(frage, 6, arten=("fakt",)) == [],
                   "eine andere Art filtert die Kette weg")

            # Eine Kette im Kreis ist ein Datenfehler - sie darf nicht haengen.
            with gedaechtnis._verbindung() as v:
                v.execute("UPDATE erinnerung SET ersetzt_durch=1 WHERE id=3")
            try:
                gedaechtnis.abrufen(frage, 6, arten=("zuhause",))
                pruefe(True, "eine Kette im Kreis haengt nicht, sie gibt auf")
            except (RecursionError, sqlite3.Error):
                pruefe(False, "eine Kette im Kreis haengt nicht, sie gibt auf")
        finally:
            gedaechtnis.DATENBANK, gedaechtnis.WERKSTATT = echt_db, echt_ws
            gedaechtnis.einbetten = echt_einbetten
    pruefe(gedaechtnis.DATENBANK == echt_db,
           "die echte Ablage ist wieder eingehaengt")


def probe_einbetter_ausfall_wird_gesagt() -> None:
    """Faellt der Einbetter aus, steht es im Journal - einmal, nicht je Frage.

    Der Rueckfall auf den Volltext allein ist vorgesehen und richtig, aber er
    findet schlechter. Eine schlechtere Antwort ohne Hinweis sieht aus wie
    eine richtige; genau deshalb blieb die Luecke oben bis zum 13.09. offen.
    """
    print("\nDer Ausfall des Einbetters wird gemeldet")
    echt_einbetten = gedaechtnis.einbetten
    echt_hook = gedaechtnis.journal_hook
    gemeldet: list[tuple] = []
    gedaechtnis.einbetten = lambda texte: None
    gedaechtnis.journal_hook = lambda art, text, **extra: gemeldet.append((art, text))
    gedaechtnis._einbetter_weg_gemeldet = False
    try:
        if gedaechtnis.DATENBANK.exists():
            for _ in range(3):
                gedaechtnis.abrufen("Welche Art Spiele habe ich?", 4)
            arten = [a for a, _ in gemeldet]
            pruefe(arten.count("einbetter_weg") == 1,
                   "drei Fragen bei Ausfall geben EINE Meldung: %s" % arten)
            pruefe(any("Volltext" in t for a, t in gemeldet
                       if a == "einbetter_weg"),
                   "und sie sagt, was jetzt stattdessen gesucht wird")
    finally:
        gedaechtnis.einbetten = echt_einbetten
        gedaechtnis.journal_hook = echt_hook
        gedaechtnis._einbetter_weg_gemeldet = False


def main() -> int:
    probe_aus_der_sitzung()
    probe_vorgaengerin()
    probe_ansprache_ohne_frage()
    probe_faecher()
    probe_ueberholt_bleibt_findbar()
    probe_einbetter_ausfall_wird_gesagt()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
