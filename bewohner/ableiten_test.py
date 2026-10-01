"""Probe fuer C - Ableiten mit Termin. Der gefaehrlichste Schritt im Plan.

    python -X utf8 ableiten_test.py          ohne Modell
    python -X utf8 ableiten_test.py --echt   dazu einmal wirklich gpt-oss

Gemessen wird vor allem, was NICHT entsteht. Ein vergessener Termin ist
aergerlich, ein erfundener weckt Calvin um drei Uhr nachts - und deshalb ist
der Trockenlauf die Voreinstellung und nicht das Gegenteil.

Alles gegen ein FESTES Jetzt: Samstag, 12.09.2026, 14:00.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS, NUTZER
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import archiv
import probenort
import sitzung

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


class Modell:
    """Liefert eine vorgegebene Liste von Sachen."""

    OHNE = object()          # "roh nicht gesetzt", unterscheidbar von None

    def __init__(self, sachen=None, roh=OHNE):
        self.sachen = sachen
        self.roh = roh
        self.aufrufe = 0
        self.prompts: list[str] = []

    def __call__(self, nachrichten):
        self.aufrufe += 1
        self.prompts.append(nachrichten[-1]["content"])
        if isinstance(self.sachen, Exception):
            raise self.sachen
        if self.roh is not Modell.OHNE:
            return self.roh
        return {"sachen": self.sachen or []}


def nichts_bekannt(text: str) -> str:
    """Ein leeres Gedaechtnis - alles ist neu."""
    return ""


def kennt(*saetze):
    """Ein Gedaechtnis, das genau diese Saetze schon hat."""
    import gedaechtnis

    def bekannt(text: str) -> str:
        kern = gedaechtnis._inhaltswoerter(text)
        for s in saetze:
            if kern and gedaechtnis.traegt_weiter(kern, s):
                return s
        return ""
    return bekannt


PAARE = [{"frage": "Ich muss morgen mit Lena zum Kinderarzt.",
          "antwort": "Ich merke es mir.", "ts": JETZT}]


def ableiten(sachen, paare=None, bekannt=nichts_bekannt, bezug=JETZT_D):
    m = Modell(sachen)
    ergebnis = archiv.ableiten("Es ging um Lenas Arzttermin.",
                               paare if paare is not None else PAARE,
                               bezug, fragen=m, bekannt=bekannt)
    return ergebnis + (m,)


# ------------------------------------------------------------------ Proben


def probe_pruefstein_des_nutzers() -> None:
    print(f"\n{NAMENS} Pruefstein: ein Termin mit Datum, kein Fakt ueber Lena")
    sachen, zurueck, m = ableiten([
        {"art": "termin", "text": f"{NAME} geht mit Lena zum Kinderarzt",
         "wann": "morgen"}])
    pruefe(len(sachen) == 1, "eine Sache: %d" % len(sachen))
    if sachen:
        s = sachen[0]
        pruefe(s["art"] == "termin", "als Termin: %s" % s["art"])
        pruefe(s["wann"] is not None
               and s["wann"].strftime("%d.%m. %H:%M") == "13.09. 09:00",
               "mit Datum 13.09. 09:00: %s"
               % (s["wann"] and s["wann"].strftime("%d.%m. %H:%M")))
    pruefe("Wortlaut" in m.prompts[0] and "Kinderarzt" in m.prompts[0],
           "der Wortlaut steht im Prompt")

    print("\ndie Uhrzeit steht oft im Text, nicht in 'wann'")
    # Genau das hat gpt-oss geliefert: wann="morgen", und "um zehn" stand im
    # Satz. Ohne Nachholen waere der Termin 09:00 - eine Stunde zu frueh.
    sachen, _, _ = ableiten([
        {"art": "termin", "wann": "morgen",
         "text": f"{NAME} geht mit Lena zum Kinderarzt um zehn"}])
    pruefe(sachen and sachen[0]["wann"].strftime("%d.%m. %H:%M")
           == "13.09. 10:00",
           "morgen + 'um zehn' im Text -> 13.09. 10:00: %s"
           % (sachen[0]["wann"].strftime("%d.%m. %H:%M") if sachen else None))
    # Eine Uhrzeit IN "wann" schlaegt die im Text - sie ist die genauere Angabe.
    sachen, _, _ = ableiten([
        {"art": "termin", "wann": "morgen um 8",
         "text": f"{NAME} geht um zehn zum Arzt"}])
    pruefe(sachen and sachen[0]["wann"].strftime("%H:%M") == "08:00",
           "'morgen um 8' schlaegt 'um zehn' im Text: %s"
           % (sachen[0]["wann"].strftime("%H:%M") if sachen else None))
    # Und der Tag wird NICHT aus dem Text nachgeholt - zwei Tageswoerter
    # koennten sich widersprechen.
    sachen, _, _ = ableiten([
        {"art": "termin", "wann": "morgen",
         "text": f"{NAME} geht übermorgen zum Arzt"}])
    pruefe(sachen and sachen[0]["wann"].day == 13,
           "'morgen' bleibt der 13., auch wenn im Text 'übermorgen' steht: %s"
           % (sachen[0]["wann"].strftime("%d.%m.") if sachen else None))

    print("\nund C.1: was schon dasteht, entsteht nicht noch einmal")
    sachen, zurueck, _ = ableiten(
        [{"art": "fakt", "text": f"Lena ist {NAMENS} Tochter"}],
        bekannt=kennt(f"{NAMENS} Tochter heißt Lena Marie."))
    pruefe(sachen == [] and zurueck,
           f"'Lena ist {NAMENS} Tochter' wird nicht angelegt: %s" % zurueck)
    pruefe(any("steht schon da" in z for z in zurueck),
           "und der Grund sagt, warum: %s" % zurueck)

    # Ist Lena UNBEKANNT, soll der Fakt entstehen - sonst versteht er beim
    # naechsten Mal nichts. Das ist der Widerspruch aus C.1.
    sachen, zurueck, _ = ableiten(
        [{"art": "fakt", "text": f"Lena ist {NAMENS} Tochter"}])
    pruefe(len(sachen) == 1 and sachen[0]["art"] == "fakt",
           "bei unbekannter Lena entsteht er: %s" % sachen)


def probe_ableitbar() -> None:
    print("\nWas ein FAKT werden darf, ist weniger als was zusammengefasst "
          "wird")
    # Die zwei Quellen, aus denen der Nachtbericht vom 12.09. Muell gemacht hat.
    paare = [
        {"frage": "Wer belegt gerade den meisten Speicher?",
         "antwort": "chrome mit 916 MB.", "ts": 1},
        {"frage": "Und wie viel ist das in Gigabyte?",
         "antwort": "916 MB sind ungefähr 0,92 GB.", "ts": 2},
        {"frage": None,
         "antwort": "Ich habe eine neue Datei cpu-z.exe gefunden.", "ts": 3},
        {"frage": "Wie heißt meine Tochter?", "antwort": "Lena Marie.", "ts": 4},
        {"frage": "Und wie alt ist sie?", "antwort": "Vier.", "ts": 5},
    ]
    fuer_satz = [str(p.get("frage")) for p in archiv.brauchbar(paare)]
    fuer_fakt = [str(p.get("frage")) for p in archiv.ableitbar(paare)]

    pruefe("Und wie viel ist das in Gigabyte?" in fuer_satz,
           "die Zusammenfassung behaelt die Folgefrage: %s" % fuer_satz)
    pruefe("Und wie viel ist das in Gigabyte?" not in fuer_fakt,
           "ein FAKT wird nicht daraus - sie erbt die Zustandsfrage: %s"
           % fuer_fakt)
    pruefe("None" in fuer_satz and "None" not in fuer_fakt,
           "die Ansprache traegt den Anlass (B9), gibt aber keinen Fakt her")
    pruefe("Und wie alt ist sie?" in fuer_fakt,
           "eine Folgefrage auf eine GUTE Frage bleibt: %s" % fuer_fakt)
    pruefe("Wie heißt meine Tochter?" in fuer_fakt,
           "und die gute Frage selbst auch")

    # Und der ganze Weg: aus so einer Sitzung entsteht kein Fakt.
    m = Modell([{"art": "fakt", "text": "916 MB sind ungefähr 0,92 GB"}])
    sachen, zurueck = archiv.ableiten("", paare[:3], JETZT_D, fragen=m,
                                      bekannt=nichts_bekannt)
    pruefe(not any("0,92" in s["text"] for s in sachen),
           "der Umrechnungssatz wird kein Fakt: %s"
           % [s["text"][:40] for s in sachen])


def probe_vorhaben() -> None:
    """Calvin am 13.09.: "er darf alles aus dem Gespraech ziehen, nur halt
    ohne meine Zustimmung nichts umbauen."

    Vorher fiel ein erkannter Auftrag heraus. Jetzt wird er FESTGEHALTEN -
    und das ist nur zu verantworten, solange von dieser Art kein Weg zu einer
    Ausfuehrung fuehrt. Genau das wird hier gemessen.
    """
    print("\nEin Auftrag wird festgehalten, nicht ausgefuehrt")
    sachen, zurueck, _ = ableiten([
        {"art": "auftrag", "text": "Die Logdateien aufraeumen"},
        {"art": "fakt", "text": "Der Drucker steht im Flur"}])
    pruefe([s["art"] for s in sachen] == ["vorhaben", "fakt"],
           "aus dem Auftrag wird ein Vorhaben, der Fakt bleibt: %s"
           % [s["art"] for s in sachen])
    pruefe(not zurueck, "nichts zurueckgehalten: %s" % zurueck)

    # Es geht ins GEDAECHTNIS, mit eigener Art - nicht in die Auftragsschlange.
    gemerkt, termine = [], []
    b = archiv.anwenden(sachen, scharf=True,
                        merken=lambda a, t, w: gemerkt.append((a, t, w)),
                        vormerken=lambda t, w: termine.append((t, w)))
    pruefe(b["vorhaben"] == 1, "eins als Vorhaben gezaehlt: %d" % b["vorhaben"])
    pruefe(("vorhaben", "Die Logdateien aufraeumen", False) in gemerkt,
           "als eigene Art im Gedaechtnis: %s" % gemerkt)
    pruefe(termine == [], "und kein Termin daraus: %s" % termine)

    # Der Riegel ist, dass es keinen Weg von hier zu einer Handlung gibt.
    quelle = Path(archiv.__file__).read_text(encoding="utf-8")
    stelle = quelle[quelle.index("def anwenden("):]
    stelle = stelle[:stelle.index("\ndef ")]
    # Ohne Docstring: der REDET ueber die Auftragsschlange, und die Suche
    # faende ihn statt eines Aufrufs.
    stelle = stelle.split('"""')[-1]
    wege = [z.strip() for z in stelle.splitlines()
            if "anlaesse" in z or "import kann" in z or "auftrag" in z.lower()]
    pruefe(not wege,
           "anwenden() kennt keinen Weg zur Ausfuehrung: %s" % wege)

    # Eine unbekannte Art ebenso - lieber melden als raten.
    sachen, zurueck, _ = ableiten([
        {"art": "handlung", "text": "Neustarten"}])
    pruefe(sachen == [] and any("unbekannte Art" in z for z in zurueck),
           "eine unbekannte Art wird gemeldet: %s" % zurueck)


def probe_termin_ohne_datum() -> None:
    print("\nEin Termin ohne Datum wird NICHT angelegt (C.5)")

    faelle = [
        ("am 3.", "unklar", True, "Monat offen -> Rueckfrage"),
        ("bald", "unklar", True, "Zeitabsicht ohne Datum -> Rueckfrage"),
        ("gestern", "kein_termin", False, "keine Terminabsicht, KEINE Rueckfrage"),
        ("", "nichts", True, "gar kein Zeitwort -> Rueckfrage"),
    ]
    for wort, erwartet, will_rueckfrage, warum in faelle:
        sachen, zurueck, _ = ableiten([
            {"art": "termin", "text": f"{NAME} hat einen Arzttermin",
             "wann": wort}])
        s = sachen[0] if sachen else {}
        pruefe(s.get("wann") is None and s.get("grund") == erwartet,
               "%-9r -> grund=%r (%s)" % (wort, s.get("grund"), warum))
        fragen = archiv.rueckfragen(sachen)
        pruefe(bool(fragen) == will_rueckfrage,
               "  Rueckfrage: %s" % (fragen[0][:64] if fragen else "keine"))

        # Und er wird in KEINEM Fall angelegt.
        termine = []
        b = archiv.anwenden(sachen, scharf=True,
                            vormerken=lambda t, w: termine.append((t, w)))
        pruefe(termine == [] and b["termine"] == 0,
               "  und angelegt wird nichts, auch scharf nicht")

    # Ein Termin MIT Datum wird scharf angelegt - sonst prueft das oben nichts.
    sachen, _, _ = ableiten([
        {"art": "termin", "text": f"{NAME} geht zum Arzt", "wann": "morgen"}])
    termine = []
    b = archiv.anwenden(sachen, scharf=True,
                        vormerken=lambda t, w: termine.append((t, w)))
    pruefe(len(termine) == 1 and b["termine"] == 1,
           "der Gegenbeweis: MIT Datum wird er angelegt: %s" % termine)


def probe_trockenlauf() -> None:
    print("\nScharf ist die Voreinstellung, der Trockenlauf bleibt erreichbar")
    pruefe(archiv.ABLEITEN_SCHARF is True,
           f"ABLEITEN_SCHARF ist an, seit {NAME} entschieden hat")
    quelle = Path(archiv.__file__).read_text(encoding="utf-8")
    pruefe('os.environ.get("ABLEITEN_SCHARF"' in quelle,
           "und die Bremse kommt aus der Umgebung, ohne Codeaenderung")

    # Der Wortlaut muss die 22 enthalten - sonst haelt wissen.mangel() die
    # Vorliebe als erfundene Zahl zurueck, und zwar zu Recht.
    gesagt = [{"frage": "Ich will keine Push nach 22 Uhr, und der Drucker "
                        "steht jetzt im Flur. Morgen muss ich zum Arzt.",
               "antwort": "Verstanden.", "ts": JETZT}]
    sachen, zurueck, _ = ableiten([
        {"art": "termin", "text": f"{NAME} geht zum Arzt", "wann": "morgen"},
        {"art": "fakt", "text": "Der Drucker steht im Flur"},
        {"art": "vorliebe", "text": f"{NAME} will keine Push nach 22 Uhr"}],
        paare=gesagt)
    pruefe(len(sachen) == 3,
           "drei Sachen abgeleitet: %d  %s" % (len(sachen), zurueck))

    termine, gemerkt, zeilen = [], [], []
    b = archiv.anwenden(sachen, scharf=False,
                        merken=lambda a, t, w: gemerkt.append((a, t, w)),
                        vormerken=lambda t, w: termine.append((t, w)),
                        journal=lambda k, t, **e: zeilen.append((k, t)))
    pruefe(b["scharf"] is False, "der Bericht sagt: nicht scharf")
    pruefe(termine == [] and gemerkt == [],
           "NICHTS angelegt - kein Termin, kein Fakt: %s %s"
           % (termine, gemerkt))
    pruefe(b["nur_gemeldet"] == 3, "drei nur gemeldet: %d" % b["nur_gemeldet"])
    pruefe(len(zeilen) == 3 and all(k == "ableiten_trocken" for k, _ in zeilen),
           "und drei Journalzeilen, die sagen was er TAETE: %s"
           % [t[:48] for _, t in zeilen])
    pruefe(any("13.09." in t for _, t in zeilen),
           "mit dem Datum, das er anlegen wuerde: %s"
           % [t for _, t in zeilen if "13.09." in t])

    print("\nund scharf legt er dieselben drei an")
    termine, gemerkt = [], []
    b = archiv.anwenden(sachen, scharf=True,
                        merken=lambda a, t, w: gemerkt.append((a, t, w)),
                        vormerken=lambda t, w: termine.append((t, w)))
    pruefe(b["termine"] == 1 and len(termine) == 1, "ein Termin: %s" % termine)
    pruefe(b["fakten"] == 1 and b["vorlieben"] == 1,
           "ein Fakt, eine Vorliebe: %d / %d" % (b["fakten"], b["vorlieben"]))
    pruefe(any(w for _, _, w in gemerkt),
           "und die Vorliebe traegt wichtig=True: %s" % gemerkt)
    pruefe(all(a == "fakt" for a, _, _ in gemerkt),
           "beide als Art `fakt` - dasselbe Fach, hoeheres Gewicht")


def probe_woraus() -> None:
    print("\nWoraus der Satz stammt - und die drei Auskuenfte darueber")
    # Calvins Satz aus dem Nachtbericht vom 13.09. Die Frage teilt kein
    # einziges Inhaltswort mit ihm; gefunden wird sie ueber die ANTWORT.
    gigabyte = [{"frage": "Und wie viel ist das in Gigabyte?",
                 "antwort": "916 MB sind ungefaehr 0,92 GB, 914 MB etwa "
                            "0,91 GB.", "ts": JETZT}]
    pruefe(archiv._woraus("916 MB sind ungefaehr 0,92 GB, 914 MB etwa 0,91 GB.",
                          gigabyte) == gigabyte[0]["frage"],
           "der lange Satz findet seine Frage")
    # Der eigentliche Punkt: Ohne die Zahlen haette dieser hier nichts.
    kern = archiv._anker("914 MB frei")
    pruefe("914" in kern,
           "die dreistellige Zahl ist ein Anker: %s" % sorted(kern))
    pruefe(archiv._woraus("914 MB frei", gigabyte) == gigabyte[0]["frage"],
           "und traegt die Zuordnung allein: %r"
           % archiv._woraus("914 MB frei", gigabyte))
    pruefe(archiv._woraus("Lena hat morgen Geburtstag", gigabyte) == "",
           "ein fremder Satz findet sie NICHT - sonst waere jede Zuordnung "
           "wertlos")

    # Drei Herkuenfte, drei Auskuenfte.
    sachen, _, _ = ableiten([{"art": "fakt",
                              "text": f"{NAME} muss mit Lena zum Kinderarzt"}])
    pruefe(sachen and sachen[0].get("woraus_art") == "frage",
           "aus einer Frage: art=%r" % (sachen and sachen[0].get("woraus_art")))

    # Eine Sitzung aus lauter Ansprachen: ableitbar() laesst nichts durch, das
    # Modell sieht nur die Zusammenfassung. Dann GIBT es keine Frage.
    fund = [{"frage": None,
             "antwort": "eine neue Datei cpu-z_2.17-en.exe im Download-Ordner",
             "ts": JETZT}]
    sachen, _, _ = ableiten([{"art": "fakt",
                              "text": "Eine neue Datei liegt im Download-"
                                      "Ordner"}], paare=fund)
    pruefe(sachen and sachen[0].get("woraus_art") == "zusammenfassung",
           "aus einer Beobachtung: art=%r"
           % (sachen and sachen[0].get("woraus_art")))

    sachen, _, _ = ableiten([{"art": "fakt", "text": "Der Drucker steht im "
                                                     "Flur"}])
    pruefe(sachen and sachen[0].get("woraus_art") == "unklar",
           "wirklich nicht zuordenbar: art=%r"
           % (sachen and sachen[0].get("woraus_art")))

    # Und die Zeile traegt es ins Journal - sonst weiss die Nacht es nicht.
    zeilen = []
    archiv.anwenden(sachen, scharf=False,
                    journal=lambda k, t, **e: zeilen.append(e))
    pruefe(zeilen and zeilen[0].get("woraus_art") == "unklar",
           "und es steht in der Journalzeile: %s" % (zeilen and zeilen[0]))


def probe_bericht_kennt_alte_zeilen() -> None:
    print("\nDer Bericht unterscheidet 'nicht gefunden' von 'nicht gefragt'")
    import io
    import contextlib
    import nacht

    def zeile(**mehr):
        e = {"ts": JETZT, "kind": "ableiten_trocken",
             "text": "WUERDE anlegen - fakt: 916 MB sind 0,92 GB"}
        e.update(mehr)
        return e

    def bericht(e):
        auf = io.StringIO()
        with contextlib.redirect_stdout(auf):
            nacht._trockenzeile(e)
        return auf.getvalue()

    alt = bericht(zeile())                      # ohne das Feld: alte Zeile
    pruefe("aelter als das" in alt,
           "eine Zeile ohne `woraus_art` gilt als alt, nicht als Fehler:\n%s"
           % alt.rstrip())
    pruefe("nicht zuordnen" not in alt,
           "und meldet KEINEN Fehler, den niemand gemessen hat")

    aus_fund = bericht(zeile(woraus="", woraus_art="zusammenfassung"))
    pruefe("Beobachtung" in aus_fund,
           "eine Beobachtung heisst Beobachtung:\n%s" % aus_fund.rstrip())

    offen = bericht(zeile(woraus="", woraus_art="unklar"))
    pruefe("nicht zuordnen" in offen,
           "und nur der echte Fall heisst 'nicht zuordnen':\n%s"
           % offen.rstrip())

    gefunden = bericht(zeile(woraus="Und wie viel ist das in Gigabyte?",
                             woraus_art="frage"))
    pruefe("Gigabyte" in gefunden, "die gefundene Frage steht woertlich da")


def probe_wachen() -> None:
    print("\nDie Wachen aus C.3 - mangel() gilt auch hier")
    # Eine erfundene Zahl.
    sachen, zurueck, _ = ableiten([
        {"art": "fakt", "text": "Der Termin ist am 17. um 14:30"}])
    pruefe(sachen == [] and any("Zahlen" in z for z in zurueck),
           "Zahlen, die im Gespraech nicht stehen: %s" % zurueck)
    # Ein Satz ueber sich selbst.
    sachen, zurueck, _ = ableiten([
        {"art": "fakt", "text": "Ich kann den Bildschirm sehen"}])
    pruefe(sachen == [] and zurueck,
           f"ueber sich selbst statt ueber {NAMENS} Welt: %s" % zurueck)
    # Eine Nacherzaehlung.
    sachen, zurueck, _ = ableiten([
        {"art": "fakt", "text": f"{NAME} fragte nach dem Termin"}])
    pruefe(sachen == [] and zurueck, "Nacherzaehlung: %s" % zurueck)

    print("\nKeine Liste, kein Absturz")
    for roh in ({}, {"sachen": "morgen"}, {"sachen": None}, None):
        m = Modell(roh=roh)
        sachen, zurueck = archiv.ableiten("x", PAARE, JETZT_D, fragen=m,
                                          bekannt=nichts_bekannt)
        pruefe(sachen == [] and zurueck,
               "%-22r -> (%d, %s)" % (roh, len(sachen), zurueck[:1]))

    m = Modell(RuntimeError("ConnectError"))
    sachen, zurueck = archiv.ableiten("x", PAARE, JETZT_D, fragen=m,
                                      bekannt=nichts_bekannt)
    pruefe(sachen == [] and any("nicht abgeleitet" in z for z in zurueck),
           "ein stolperndes Modell gibt einen Grund, keinen Absturz: %s"
           % zurueck)

    print("\nEine leere Liste ist eine richtige Antwort")
    sachen, zurueck, _ = ableiten([])
    pruefe(sachen == [], "nichts Neues -> nichts abgeleitet")


def probe_im_abschluss() -> None:
    print("\nIm Abschluss: die Marke, und nur EINMAL")
    ordner = probenort.ablage("ableiten")
    sitzung.WERKSTATT = ordner
    sitzung.KOEPFE = ordner / "sitzungen.jsonl"
    sitzung.ORDNER = ordner / "sitzungen"
    try:
        sid = sitzung.sitzung_fuer(JETZT, NUTZER)
        sitzung.paar_anhaengen(sid, "Ich muss morgen mit Lena zum Arzt.",
                               "Ich merke es mir.", JETZT)

        class Beides:
            """Zusammenfassen UND Ableiten, an der Form unterscheidbar."""

            def __init__(self):
                self.aufrufe = 0

            def __call__(self, nachrichten):
                self.aufrufe += 1
                if "Du fasst ein Gespraech zusammen" in nachrichten[0][
                        "content"]:
                    return {"zusammenfassung": "Es ging um Lenas Arzttermin."}
                return {"sachen": [{"art": "termin",
                                    "text": f"{NAME} geht mit Lena zum Arzt",
                                    "wann": "morgen"}]}

        m = Beides()
        zeilen = []
        # merken_sache UND vormerken MUESSEN mit: Ohne sie legt der scharfe
        # Betrieb den abgeleiteten Termin wirklich an - am 13.09. um 12:12
        # stand dieser hier in der echten erinnerungen.json.
        vorgemerkt, sachen_gemerkt = [], []
        b = archiv.abschliessen(sid, JETZT + 11 * MIN, fragen=m,
                                merken=lambda a, t, s: 1,
                                merken_sache=lambda a, t, w:
                                    sachen_gemerkt.append((a, t, w)),
                                vormerken=lambda t, w:
                                    vorgemerkt.append((t, w)),
                                journal=lambda k, t, **e: zeilen.append((k, t)))
        pruefe(m.aufrufe == 2, "zwei Aufrufe: zusammenfassen und ableiten")
        abgeleitet = b.get("abgeleitet") or {}
        pruefe(abgeleitet.get("sachen") == 1,
               "eine Sache abgeleitet: %s" % abgeleitet.get("sachen"))
        pruefe(abgeleitet.get("scharf") is True, "scharf")
        pruefe(len(vorgemerkt) == 1 and vorgemerkt[0][1].day == 13,
               "der Termin wird vorgemerkt, auf den 13.: %s" % vorgemerkt)
        k = sitzung.kopf(sid)
        pruefe(k["abgeleitet"] == "1 Termine, 0 Fakten, 0 Vorlieben, 0 Vorhaben",
               "die Marke traegt, WAS er getan hat: %r" % k["abgeleitet"])
        pruefe(sachen_gemerkt == [],
               "und nichts ins Gedaechtnis, es war nur ein Termin: %s"
               % sachen_gemerkt)

        # Ein zweiter Abschluss leitet NICHT erneut ab.
        vorher = m.aufrufe
        b2 = archiv.abschliessen(sid, JETZT + 20 * MIN, fragen=m,
                                 merken=lambda a, t, s: 1)
        pruefe((b2.get("abgeleitet") or {}).get("uebersprungen")
               == "schon abgeleitet",
               "der zweite Lauf leitet nicht erneut ab: %s"
               % (b2.get("abgeleitet") or {}))
        pruefe(m.aufrufe == vorher + 1,
               "und kostet nur den Aufruf fuers Zusammenfassen: %d -> %d"
               % (vorher, m.aufrufe))
    finally:
        probenort.wegraeumen(ordner)


def probe_echt() -> None:
    print(f"\nEinmal wirklich gpt-oss - {NAMENS} Satz")
    paare = [{"frage": "Ich muss morgen mit Lena zum Kinderarzt, um zehn.",
              "antwort": "Ich merke es mir.", "ts": JETZT}]
    sachen, zurueck = archiv.ableiten(
        "Es ging um Lenas Termin beim Kinderarzt.", paare, JETZT_D,
        bekannt=nichts_bekannt)
    for s in sachen:
        print("    %-9s %s%s" % (s["art"], s["text"],
                                 "  [%s]" % s["wann"].strftime("%d.%m. %H:%M")
                                 if s.get("wann") else ""))
    for z in zurueck:
        print("    (zurueck) %s" % z)
    termine = [s for s in sachen if s["art"] == "termin"]
    pruefe(bool(termine), "er leitet einen Termin ab: %s" % (zurueck or "ok"))
    if termine:
        wann = termine[0].get("wann")
        pruefe(wann is not None and wann.day == 13,
               "am 13.09.: %s" % (wann and wann.strftime("%d.%m. %H:%M")))
        pruefe(wann is not None and wann.hour == 10,
               "und um zehn, nicht um neun: %s"
               % (wann and wann.strftime("%H:%M")))
    pruefe(not any(s["art"] == "auftrag" for s in sachen),
           "und kein Auftrag")


def main() -> int:
    probe_pruefstein_des_nutzers()
    probe_ableitbar()
    probe_vorhaben()
    probe_termin_ohne_datum()
    probe_trockenlauf()
    probe_woraus()
    probe_bericht_kennt_alte_zeilen()
    probe_wachen()
    probe_im_abschluss()
    if "--echt" in sys.argv:
        probe_echt()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
