"""Probe fuer archiv.py - Schritt B.

    python archiv_test.py          ohne Modell, mit einem Aufruf als Parameter
    python archiv_test.py --echt   dazu: einmal wirklich gpt-oss fragen

Das Modell wird ueber `fragen=` hereingegeben, nicht ueber die Leitung geholt.
Der Grund steht in archiv.zusammenfassen() und ist ein Fehler von heute
frueh: kann_test.py hat monatelang "bestanden" gemeldet fuer einen Aufruf,
den es im Betrieb gar nicht gab.

Geprueft wird, was der Plan unter "Proben, je Schritt eine" fuer B verlangt:
Abschluss nach Neustart, eine Sitzung aus lauter Zustandsfragen fragt kein
Modell, der Wortlaut bleibt, die Marken - dazu B11 (drei faellige Sitzungen
ergeben EINEN Modellaufruf) und der Schalter PROTOKOLL_ALT.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS, NUTZER
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import archiv
import probenort
import sitzung
import wissen

GESAMT = 0
FEHLER = 0

JETZT_D = datetime(2026, 9, 12, 14, 0)
JETZT = JETZT_D.timestamp()
MIN = 60.0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def frisch() -> Path:
    ordner = probenort.ablage("archiv")
    sitzung.WERKSTATT = ordner
    sitzung.KOEPFE = ordner / "sitzungen.jsonl"
    sitzung.ORDNER = ordner / "sitzungen"
    return ordner


def wegraeumen() -> None:
    """Raeumt den Probenordner weg - und NUR den.

    GENAU HIER war die Luecke: main() raeumt nach jeder Probe
    sitzung.WERKSTATT weg, aber die erste Probe bog den Pfad nie um. Beim
    ersten Schleifendurchlauf zeigte er noch auf werkstatt\\, und rmtree hat am
    12.09. gegen 21:00 131 Erinnerungen, die Chronik und die Termine geloescht.

    Der Riegel steht jetzt in probe.py - an der Stelle, die loescht, nicht in
    dieser Datei. Hier stand er zuerst, und das war zu wenig: Jede andere
    Probe konnte denselben Fehler wieder machen.
    """
    probenort.wegraeumen(sitzung.WERKSTATT)


class Modell:
    """Ein Modell, das mitzaehlt, wie oft es gefragt wurde."""

    def __init__(self, antwort="Es ging um Lenas Termin beim Kinderarzt."):
        self.antwort = antwort
        self.aufrufe = 0
        self.prompts: list[str] = []

    def __call__(self, nachrichten):
        self.aufrufe += 1
        self.prompts.append(nachrichten[-1]["content"])
        if isinstance(self.antwort, Exception):
            raise self.antwort
        return {"zusammenfassung": self.antwort}


class Gedaechtnis:
    """Statt der echten Datenbank. Zweimal ist an genau dieser Stelle heute
    schon eine Probe ins Echte gelaufen."""

    def __init__(self):
        self.eintraege: list[tuple] = []

    def __call__(self, art, text, sid):
        self.eintraege.append((art, text, sid))
        return len(self.eintraege)


def P(paare) -> list[dict]:
    """Aus (Frage, Antwort) werden Paare, wie sie in der Sitzung stehen."""
    return [{"frage": f, "antwort": a, "ts": JETZT + i}
            for i, (f, a) in enumerate(paare)]


def sitzung_mit(paare, ts=JETZT, von=NUTZER) -> str:
    sid = sitzung.sitzung_fuer(ts, von)
    for i, (f, a) in enumerate(paare):
        sitzung.paar_anhaengen(sid, f, a, ts + i)
    return sid


# ------------------------------------------------------------------ Proben


def probe_was_hineingehoert() -> None:
    print("\nder Gegenstand, nicht der Ablauf (B.3)")
    frisch()
    paare = P([("Wann ist Lena beim Kinderarzt?", "Am Montag um zehn."),
               ("Und die Unterlagen?", "Die Versichertenkarte reicht.")])
    m = Modell("Es ging um Lenas Termin beim Kinderarzt und die Unterlagen.")
    satz, zurueck = archiv.zusammenfassen(paare, fragen=m)
    pruefe(satz.startswith("Es ging um"), "die Zusammenfassung steht: %s" % satz)
    pruefe(zurueck == [], "nichts zurueckgehalten")
    pruefe(f"{NAME}: Wann ist Lena" in m.prompts[0]
           and "Du: Am Montag" in m.prompts[0],
           "beide Seiten stehen im Prompt")

    # Die Wache: eine Zusammenfassung, die das Gespraech nacherzaehlt.
    m = Modell(f"{NAME} fragte nach dem Termin, ich habe geantwortet.")
    satz, zurueck = archiv.zusammenfassen(paare, fragen=m)
    pruefe(satz == "" and zurueck and "nach" in zurueck[0].lower(),
           f"'{NAME} fragte ...' wird zurueckgehalten: %s" % zurueck)

    # Und die Wache gegen erfundene Zahlen.
    m = Modell("Es ging um Lenas Termin am 17. um 14:30 Uhr.")
    satz, zurueck = archiv.zusammenfassen(paare, fragen=m)
    pruefe(satz == "" and zurueck and "Zahlen" in zurueck[0],
           "Zahlen, die im Gespraech nicht stehen: %s" % zurueck)

    # Aber die Laengengrenze des FAKTS darf nicht gelten - sonst waere jede
    # Zusammenfassung "eine Erzaehlung, kein Fakt".
    lang = ("Es ging um Lenas Termin beim Kinderarzt, um die Unterlagen "
            "dafuer und darum, wer sie hinbringt. " * 2).strip()
    pruefe(len(lang) > wissen.FAKT_ZEICHEN_MAX,
           "der Pruefsatz ist laenger als ein Fakt (%d Zeichen)" % len(lang))
    satz, zurueck = archiv.zusammenfassen(paare, fragen=Modell(lang))
    pruefe(satz == lang, "und wird trotzdem durchgelassen: %s" % zurueck)

    # Ueber 600 aber nicht mehr.
    zu_lang = "Es ging um " + "x" * 700
    satz, zurueck = archiv.zusammenfassen(paare, fragen=Modell(zu_lang))
    pruefe(satz == "" and zurueck, "ueber 600 Zeichen nicht: %s" % zurueck)


def probe_zustandsfragen() -> None:
    print("\neine Sitzung aus lauter Zustandsfragen fragt kein Modell (B.3)")
    frisch()
    g = Gedaechtnis()
    m = Modell()
    sid = sitzung_mit([("Wie spät ist es?", "Es ist 18 Uhr 54."),
                       ("Und wie viel Platz ist noch frei?",
                        "Auf C liegen noch 1537 Gigabyte frei."),
                       ("Wer belegt gerade den meisten Speicher?",
                        "llama-server mit 1,2 GB.")])
    b = archiv.abschliessen(sid, JETZT + 11 * MIN, fragen=m, merken=g)
    pruefe(m.aufrufe == 0, "das Modell wurde GAR NICHT gefragt: %d Aufrufe"
           % m.aufrufe)
    pruefe(b["zusammenfassung"] == "" and g.eintraege == [],
           "nichts ins Gedaechtnis: %s" % g.eintraege)
    k = sitzung.kopf(sid)
    pruefe(k["zusammenfassung"] == "",
           "die Marke steht auf LEER, nicht auf null - sonst holt die Nacht "
           "sie jede Nacht wieder: %r" % k["zusammenfassung"])
    pruefe(k["geschlossen"] == JETZT + 11 * MIN, "geschlossen ist gesetzt")
    pruefe(len(sitzung.paare(sid)) == 3,
           "und der Wortlaut liegt vollstaendig da - zehn 'Wie spaet ist es?' "
           "kosten nichts, sind aber nachlesbar")


def probe_marken_und_wortlaut() -> None:
    print("\nMarken und Wortlaut (A.4, B.4)")
    frisch()
    g, m = Gedaechtnis(), Modell()
    sid = sitzung_mit([("Wann ist Lena beim Kinderarzt?", "Am Montag um zehn.")])
    b = archiv.abschliessen(sid, JETZT + 11 * MIN, fragen=m, merken=g)

    # ZWEI Aufrufe seit C: einer fuers Zusammenfassen, einer fuers Ableiten.
    # Vorher stand hier 1 - die Zahl hat sich geaendert, weil C dazugekommen
    # ist, nicht weil etwas doppelt laeuft. Die Probe auf B11 (drei faellige
    # Sitzungen = EIN Durchgang) prueft das Gegenteil und gilt weiter.
    pruefe(m.aufrufe == 2, "zwei Modellaufrufe: zusammenfassen und ableiten")
    pruefe(b["gemerkt"] == 1 and g.eintraege[0][0] == "sitzung",
           "ins Gedaechtnis als Art `sitzung`: %s" % (g.eintraege[0],))
    k = sitzung.kopf(sid)
    pruefe(k["zusammenfassung"] == m.antwort,
           "die Marke traegt den Satz: %s" % k["zusammenfassung"])
    pruefe(k["abgeleitet"] == "0 Termine, 0 Fakten, 0 Vorlieben, 0 Vorhaben",
           "abgeleitet traegt, was angelegt wurde - nicht null: %r"
           % k["abgeleitet"])
    pruefe(k["geprueft"] is None, "geprueft bleibt null - das ist D")
    pruefe(sitzung.paare(sid)[0]["frage"] == "Wann ist Lena beim Kinderarzt?",
           "der Wortlaut bleibt, woertlich")

    print("\ndas Modell antwortet nicht: die Marke bleibt null (Anhang 3)")
    frisch()
    g = Gedaechtnis()
    kaputt = Modell(RuntimeError("ConnectError"))
    sid = sitzung_mit([("Was machen wir am Wochenende?", "Schwimmen.")])
    b = archiv.abschliessen(sid, JETZT + 11 * MIN, fragen=kaputt, merken=g)
    k = sitzung.kopf(sid)
    pruefe(k["geschlossen"] is not None,
           "geschlossen ist gesetzt - der Anspruch steht VOR der Arbeit")
    pruefe(k["zusammenfassung"] is None,
           "die Zusammenfassung bleibt null, damit die Nacht es nachholt: %r"
           % k["zusammenfassung"])
    pruefe(g.eintraege == [] and b["zurueckgehalten"],
           "und nichts Halbes im Gedaechtnis: %s" % b["zurueckgehalten"])


# Was eine Sitzung an Modellaufrufen kostet: zusammenfassen (B) und ableiten
# (C). B11 prueft, dass je Durchlauf EINE Sitzung dran ist - nicht, wie viele
# Aufrufe eine kostet. Als Konstante, damit die Probe bei der naechsten Stufe
# nicht wieder an der Zahl bricht, sondern an der Aussage.
JE_SITZUNG = 2


def probe_eine_je_durchlauf() -> None:
    print("\ndrei faellige Sitzungen, EINE je Durchlauf (B11 des Mac)")
    frisch()
    g, m = Gedaechtnis(), Modell()
    ids = [sitzung_mit([("Frage %d" % i, "Antwort %d" % i)],
                       ts=JETZT - (5 - i) * 3600, von="gerät%d" % i)
           for i in range(3)]
    pruefe(len(sitzung._offen_alle()) == 3, "drei offene nach dem Ausfall")

    b = archiv.durchgang(JETZT, fragen=m, merken=g)
    pruefe(m.aufrufe == JE_SITZUNG,
           "ein Durchlauf, EINE Sitzung (%d Aufrufe): %d"
           % (JE_SITZUNG, m.aufrufe))
    pruefe(b["id"] == ids[0], "und zwar die aelteste: %s" % b["id"])
    pruefe(len(sitzung._offen_alle()) == 2, "zwei bleiben offen")

    archiv.durchgang(JETZT, fragen=m, merken=g)
    archiv.durchgang(JETZT, fragen=m, merken=g)
    pruefe(m.aufrufe == 3 * JE_SITZUNG and len(sitzung._offen_alle()) == 0,
           "drei Durchlaeufe, drei Sitzungen, nichts offen: %d Aufrufe"
           % m.aufrufe)
    pruefe(archiv.durchgang(JETZT, fragen=m, merken=g) is None,
           "danach ist nichts mehr faellig")
    pruefe(m.aufrufe == 3 * JE_SITZUNG,
           "und kein Aufruf ins Leere: %d" % m.aufrufe)


def probe_neustart() -> None:
    print("\nAbschluss nach Neustart, und die Ausnahme aus B.2")
    frisch()
    g, m = Gedaechtnis(), Modell()
    # Ein Gespraech von vor einer Stunde, der Prozess war dazwischen aus.
    alt = sitzung_mit([("Wie war das mit der Bruecke?", "Sie laeuft.")],
                      ts=JETZT - 3600)
    # Und eines von vor zwei Minuten - Calvin hat nur neu gestartet.
    neu = sitzung_mit([("Bist du wieder da?", "Ja.")], ts=JETZT - 2 * MIN,
                      von="handy")

    b = archiv.durchgang(JETZT, fragen=m, merken=g)
    pruefe(b and b["id"] == alt, "die alte wird geschlossen: %s" % (b or {}).get("id"))
    pruefe(sitzung.kopf(neu)["geschlossen"] is None,
           "die frische bleibt offen - er redet vielleicht gleich weiter")
    pruefe(archiv.durchgang(JETZT, fragen=m, merken=g) is None,
           "und sie wird nicht angefasst")
    pruefe(m.aufrufe == 2,
           "eine Sitzung insgesamt, also zwei Aufrufe: %d" % m.aufrufe)


def probe_ansprache() -> None:
    print("\neine Ansprache hat keine Frage - und faellt trotzdem nicht durch")
    frisch()
    g, m = Gedaechtnis(), Modell("Es ging um die Bruecke, die weg war.")
    sid = sitzung.ansprache_eroeffnet(
        "Die Bruecke zum Mac ist seit zehn Minuten weg.", JETZT)
    b = archiv.abschliessen(sid, JETZT + 11 * MIN, fragen=m, merken=g)
    pruefe(m.aufrufe == 2,
           "das Modell wird gefragt, obwohl keine Frage vorliegt: %d"
           % m.aufrufe)
    pruefe("Du, von dir aus: Die Bruecke" in m.prompts[0],
           "und im Prompt steht, dass ER angefangen hat: %s"
           % m.prompts[0][:60])
    pruefe(b["zusammenfassung"] == m.antwort, "es gibt eine Zusammenfassung")

    # Gegenprobe: wissen.lohnt() allein haette sie verworfen.
    pruefe(not wissen.lohnt({"frage": None, "antwort": "Die Bruecke ist weg."}),
           "lohnt() allein wirft sie weg - deshalb archiv.brauchbar()")
    pruefe(len(archiv.brauchbar(sitzung.paare(sid))) == 1,
           "brauchbar() behaelt sie")


def probe_ueberholen() -> None:
    print("\nwieder aufgenommen und neu zusammengefasst: ueberholen, nicht loeschen")
    frisch()
    g = Gedaechtnis()
    sid = sitzung_mit([("Wann ist Lena beim Kinderarzt?", "Am Montag.")])
    archiv.abschliessen(sid, JETZT + 11 * MIN,
                        fragen=Modell("Es ging um Lenas Termin."), merken=g)
    erste = sitzung.kopf(sid)["zusammenfassung"]

    # Tage spaeter steigt er wieder ein.
    spaeter = JETZT + 3 * 24 * 3600
    sitzung.sitzung_fuer(spaeter, NUTZER, gewuenscht=sid)
    sitzung.paar_anhaengen(sid, "Und wer bringt sie hin?", "Du.", spaeter)
    pruefe(sitzung.kopf(sid)["zusammenfassung"] == erste,
           "beim Wiederaufnehmen bleibt die alte Zusammenfassung stehen")

    archiv.abschliessen(sid, spaeter + 11 * MIN,
                        fragen=Modell("Es ging um Lenas Termin und die Fahrt."),
                        merken=g)
    k = sitzung.kopf(sid)
    pruefe(k["zusammenfassung"] == "Es ging um Lenas Termin und die Fahrt.",
           "danach steht die neue da: %s" % k["zusammenfassung"])
    pruefe(len(g.eintraege) == 2,
           "und im Gedaechtnis liegen BEIDE - die alte ueberholt, nicht "
           "geloescht: %d" % len(g.eintraege))
    pruefe(len(sitzung.paare(sid)) == 2, "der Wortlaut hat beide Paare")


def probe_schalter() -> None:
    print("\nder Schalter PROTOKOLL_ALT (Rueckweg fuer Schritt 3)")
    frisch()
    import gespraech
    pruefe(gespraech.PROTOKOLL_ALT is False,
           "standardmaessig AUS - die Zusammenfassung ersetzt die Mitschrift")
    quelle = Path("gespraech.py").read_text(encoding="utf-8")
    pruefe("if dauerhaft and PROTOKOLL_ALT:" in quelle,
           "und er haengt an genau der einen Stelle, an der etwas wegfaellt")
    pruefe('os.environ.get("PROTOKOLL_ALT"' in quelle,
           "aus der Umgebung, ohne Codeaenderung umlegbar")


def echt() -> None:
    print("\n--echt: einmal wirklich gpt-oss fragen")
    paare = P([("Wann ist Lena beim Kinderarzt?", "Am Montag um zehn Uhr."),
               ("Und was muss ich mitbringen?", "Die Versichertenkarte reicht."),
               ("Wie spät ist es?", "Es ist 21 Uhr 12.")])
    t0 = time.time()
    satz, zurueck = archiv.zusammenfassen(paare)
    print("    %.1f s: %s" % (time.time() - t0, satz or zurueck))
    pruefe(satz, "es kommt eine Zusammenfassung")
    pruefe(len(satz) <= archiv.ZUSAMMENFASSUNG_ZEICHEN_MAX,
           "unter 600 Zeichen: %d" % len(satz))
    pruefe("Kinderarzt" in satz or "Termin" in satz or "Arzt" in satz,
           "und sie handelt vom Gegenstand")
    pruefe("21" not in satz and "Uhr" not in satz,
           "die Uhrzeitfrage ist ausgesiebt worden: %s" % satz)


def probe_herkunft_im_journal() -> None:
    """Die Journalzeile traegt den Absender - sonst kann die Chronik nicht
    unterscheiden, ob ein Gespraech Calvins war oder eine Messung.

    Am 13.09. erzaehlte sie ihm die vier Fragen aus zuhause_probe.py als seine
    Nacht: "22:30 diskutierte man ueber Spielarten und Desktop". Der Absender
    stand im Kopf der Sitzung - er kam nur nie bis ins Journal.
    """
    print("\nder Absender kommt mit ins Journal")
    frisch()
    g = Gedaechtnis()
    m = Modell()
    zeilen = []
    sid = sitzung_mit([("Was liegt auf meinem Desktop?", "Acht Verknuepfungen."),
                       ("Und was ist ComfyUI?", "Eine Oberflaeche.")])
    archiv.abschliessen(sid, JETZT + 11 * MIN, fragen=m, merken=g,
                        journal=lambda art, text, **extra:
                            zeilen.append((art, extra)))
    # abschliessen() schreibt mehr als eine Zeile - C haengt das Ableiten an.
    # Gefragt ist die Sitzungszeile.
    sitzungszeilen = [(a, x) for a, x in zeilen if a == "sitzung"]
    pruefe(len(sitzungszeilen) == 1,
           "eine Sitzungszeile unter %d Zeilen: %s"
           % (len(zeilen), [a for a, _ in zeilen]))
    art, extra = sitzungszeilen[0]
    pruefe("von" in extra,
           "sie hat ein Feld `von` - ohne das ist die Herkunft verloren: %s"
           % sorted(extra))
    pruefe(extra.get("von") == NUTZER,
           "und es ist der Absender aus dem Kopf der Sitzung: %r"
           % extra.get("von"))

    # Und die stumme Zeile genauso: Eine Sitzung ohne Zusammenfassung kann
    # ebenso aus einer Messung stammen.
    zeilen.clear()
    still = sitzung_mit([("Wie spät ist es?", "Es ist 18 Uhr 54.")],
                        ts=JETZT + 40 * MIN)
    archiv.abschliessen(still, JETZT + 51 * MIN, fragen=m, merken=g,
                        journal=lambda art, text, **extra:
                            zeilen.append((art, extra)))
    stille = [(a, x) for a, x in zeilen if a == "sitzung_still"]
    pruefe(len(stille) == 1 and "von" in stille[0][1],
           "auch die stumme Zeile traegt den Absender: %s"
           % (str(stille[0]) if stille else [a for a, _ in zeilen],))

    # Und eine Sitzung, die NICHT Calvins ist, bekommt keine Erinnerung. Die
    # Tabelle `erinnerung` hat kein `von` - was hier hineinkommt, ist spaeter
    # nicht mehr als Messung zu erkennen, und der Rueckblick erzaehlte am
    # 13.09. "die Diskussion ueber Spielarten" als Calvins Gespraech.
    #
    # `von: "test"` laesst sich nicht auf dem normalen Weg herstellen - Regel 0
    # gibt dafuer keine Sitzung, und `von` ist keine nachtraeglich setzbare
    # Marke. Also wird der Kopf fuer diesen einen Aufruf untergeschoben. Genau
    # das ist der Fall, um den es geht: eine Zusammenfassung, die aus einer
    # Messung stammt.
    #
    # NICHT mit "mac" oder "handy" geprueft - das sind GERAETE, auf denen
    # Calvin selbst spricht. Die erste Fassung dieser Wache hielt alles ausser
    # "calvin" fuer fremd und haette sein Handy ausgeschlossen;
    # probe_eine_je_durchlauf hat es gefangen.
    zeilen.clear()
    g2 = Gedaechtnis()
    fremd = sitzung_mit([("Welche Art Spiele habe ich?", "Horror und Shooter.")],
                        ts=JETZT + 80 * MIN)
    echter_kopf = sitzung.kopf
    sitzung.kopf = lambda sid: (dict(echter_kopf(sid), von="test")
                                if sid == fremd else echter_kopf(sid))
    try:
        b = archiv.abschliessen(fremd, JETZT + 91 * MIN,
                                fragen=Modell("Es ging um Spielarten."),
                                merken=g2,
                                journal=lambda art, text, **extra:
                                    zeilen.append((art, extra)))
    finally:
        sitzung.kopf = echter_kopf
    pruefe(g2.eintraege == [],
           "eine Messsitzung bekommt KEINE Erinnerung: %s" % g2.eintraege)
    pruefe(bool(b.get("nicht_gemerkt")),
           "und der Bericht sagt, warum: %r" % b.get("nicht_gemerkt"))
    pruefe(any(a == "sitzung_fremd" for a, _ in zeilen),
           "das Journal nennt sie als fremd: %s" % [a for a, _ in zeilen])
    pruefe(sitzung.kopf(fremd)["zusammenfassung"] == "Es ging um Spielarten.",
           "die Zusammenfassung steht trotzdem am Kopf - sie ist nicht falsch, "
           f"sie gehoert nur nicht in {NAMENS} Gedaechtnis")

    # Und das Gegenstueck: ein GERAET ist Calvin. Eine Sitzung vom Handy
    # bekommt ihre Erinnerung wie jede andere.
    zeilen.clear()
    g3 = Gedaechtnis()
    # Eine INHALTLICHE Frage: "Wie warm wird die Karte?" ist eine
    # Zustandsfrage, und die wirft `brauchbar()` nach B.3 weg - dann entsteht
    # gar keine Zusammenfassung, und die Probe haette nichts gemessen.
    vom_handy = sitzung_mit([("Wann ist Lena beim Zahnarzt?", "Am Donnerstag.")],
                            ts=JETZT + 120 * MIN, von="handy")
    archiv.abschliessen(vom_handy, JETZT + 131 * MIN,
                        fragen=Modell("Es ging um Lenas Zahnarzttermin."),
                        merken=g3,
                        journal=lambda art, text, **extra:
                            zeilen.append((art, extra)))
    pruefe(len(g3.eintraege) == 1,
           f"eine Sitzung vom Handy ist {NAMENS} und wird gemerkt: %s"
           % g3.eintraege)
    pruefe(not any(a == "sitzung_fremd" for a, _ in zeilen),
           "und gilt nicht als fremd: %s" % [a for a, _ in zeilen])


def main() -> int:
    print("Probe archiv - festes Jetzt: %s"
          % JETZT_D.strftime("%A, %d.%m.%Y, %H:%M"))
    for probe in (probe_was_hineingehoert, probe_zustandsfragen,
                  probe_marken_und_wortlaut, probe_eine_je_durchlauf,
                  probe_neustart, probe_ansprache, probe_ueberholen,
                  probe_schalter, probe_herkunft_im_journal):
        probe()
        wegraeumen()
    if "--echt" in sys.argv:
        echt()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
