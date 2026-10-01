"""Probe fuer D - die naechtliche Gegenpruefung.

    python -X utf8 pruefung_test.py

Sie muss drei Dinge beweisen, und das dritte ist das schwerste:
  erkennt sie, was liegengeblieben ist?
  legt sie vor, statt zu handeln - und loescht sie nichts?
  kommt derselbe Verdacht NICHT jede Nacht wieder (B7)?

Das dritte entscheidet, ob sie ueberlebt: Eine Pruefung, die jeden Morgen
dasselbe meldet, wird abgeschaltet, und dann prueft nichts mehr.

Alles gegen ein FESTES Jetzt: Sonntag, 13.09.2026, 02:30.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS, NUTZER
import sys
from datetime import datetime
from pathlib import Path

import pruefstand
pruefstand.werkzeuge_einbinden()

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
import gedaechtnis
import probenort
import pruefung
import sitzung

GESAMT = 0
FEHLER = 0

# Zwei Uhr dreissig in der Nacht auf Sonntag - die Stunde, die Calvin nennt.
NACHT = datetime(2026, 9, 13, 2, 30).timestamp()
TAGS = datetime(2026, 9, 12, 14, 0).timestamp()
MIN = 60.0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def frisch() -> Path:
    ordner = probenort.ablage("pruefung")
    sitzung.WERKSTATT = ordner
    sitzung.KOEPFE = ordner / "sitzungen.jsonl"
    sitzung.ORDNER = ordner / "sitzungen"
    pruefung.WERKSTATT = ordner
    pruefung.MARKE = ordner / "_pruefung_zuletzt"
    pruefung.ZUSTAND = ordner / "pruefung.json"
    # DAS GEDAECHTNIS AUCH. `pruefung.nachholen` ruft `archiv.abschliessen`
    # OHNE `merken=`, und ohne diese drei Zeilen landet die Zusammenfassung im
    # echten gedaechtnis.db: Bis zum 13.09. legte jeder Lauf dieser Probe eine
    # Erinnerung an "Lenas Arzttermin" an, und siebzehn davon lagen am Morgen
    # darin - aus einer Sitzung, die Calvin nie gefuehrt hat. Die Probe bog
    # die Sitzungen um und das Gedaechtnis nicht; gesehen hat das niemand,
    # weil das Schreiben stumm gelang.
    gedaechtnis.WERKSTATT = ordner
    gedaechtnis.DATENBANK = ordner / "gedaechtnis.db"
    gedaechtnis.KERNWISSEN = ordner / "ERINNERUNG.md"
    # UND DIE TERMINLISTE. Seit das Ableiten scharf ist, legt
    # `archiv.anwenden` einen abgeleiteten Termin ueber `erinnern` an - ein
    # zweiter Schreibweg, den diese Probe nicht umgebogen hatte. Beim ersten
    # scharfen Lauf am 13.09. stand ein erfundener Arzttermin in der echten
    # erinnerungen.json.
    sys.path.insert(0, str(Path(__file__).parent / "werkstatt" / "werkzeuge"))
    import erinnern
    erinnern.WERKSTATT_ORDNER = str(ordner)
    erinnern.DATEI = str(ordner / "erinnerungen.json")
    return ordner


def probe_faellig() -> None:
    print("\nEinmal je Nacht, und erst ab zwei Uhr")
    ordner = frisch()
    try:
        pruefe(pruefung.STUNDE_AB == 2, "ab 2 Uhr, nicht ab 5 wie der "
                                        "Rueckblick: %d" % pruefung.STUNDE_AB)
        pruefe(pruefung.faellig(NACHT), "um 2:30 faellig")
        pruefe(not pruefung.faellig(datetime(2026, 9, 13, 1, 0).timestamp()),
               "um 1:00 noch nicht")
        # BEIDE Grenzen. Ohne die obere war sie von 2 Uhr bis Mitternacht
        # faellig und ist darum am 12.09. um 23:40 gelaufen, nicht nachts.
        for stunde in (5, 9, 14, 20, 23):
            pruefe(not pruefung.faellig(
                       datetime(2026, 9, 13, stunde, 30).timestamp()),
                   "um %02d:30 NICHT - die Nacht ist vorbei" % stunde)
        pruefe(pruefung.STUNDE_BIS <= 5,
               "das Fenster endet, bevor der Rueckblick um 5 anfaengt: %d"
               % pruefung.STUNDE_BIS)
        pruefung._marke_setzen(NACHT)
        pruefe(not pruefung.faellig(NACHT + 600),
               "und nach dem Lauf nicht noch einmal - ein Neustart um 2:40 "
               "laesst sie nicht zweimal laufen")
        pruefe(pruefung.faellig(NACHT + 24 * 3600),
               "in der naechsten Nacht um 2:30 wieder - NICHT 21 Stunden "
               "spaeter, das waere 23:30 und liegt ausserhalb des Fensters")
    finally:
        probenort.wegraeumen(ordner)


def probe_liegengeblieben() -> None:
    print("\nWas liegengeblieben ist - ohne Modell erkennbar (D.2.1)")
    ordner = frisch()
    try:
        # Eine geschlossene ohne Zusammenfassung: das Modell war stumm.
        a = sitzung.sitzung_fuer(TAGS, NUTZER)
        sitzung.paar_anhaengen(a, "Frage A", "Antwort A", TAGS)
        sitzung.schliessen(a, TAGS + 11 * MIN)
        # Eine zusammengefasste ohne Ableitung: C gab es noch nicht.
        b = sitzung.sitzung_fuer(TAGS + 3600, "handy")
        sitzung.paar_anhaengen(b, "Frage B", "Antwort B", TAGS + 3600)
        sitzung.schliessen(b, TAGS + 3600 + 11 * MIN)
        sitzung.marke_setzen(b, "zusammenfassung", "Es ging um B.")
        # Und eine vollstaendige: die darf NICHT auffallen.
        c = sitzung.sitzung_fuer(TAGS + 7200, "tablet")
        sitzung.paar_anhaengen(c, "Frage C", "Antwort C", TAGS + 7200)
        sitzung.schliessen(c, TAGS + 7200 + 11 * MIN)
        sitzung.marke_setzen(c, "zusammenfassung", "Es ging um C.")
        sitzung.marke_setzen(c, "abgeleitet", "trocken: 0")

        befunde = pruefung.liegengeblieben(sitzung.lesen())
        arten = {x["art"]: x["sid"] for x in befunde}
        pruefe(arten.get("ohne_zusammenfassung") == a,
               "die ohne Zusammenfassung faellt auf: %s" % arten)
        pruefe(arten.get("ohne_ableitung") == b,
               "die ohne Ableitung auch: %s" % arten)
        pruefe(len(befunde) == 2,
               "und die vollstaendige NICHT: %d Befunde" % len(befunde))
    finally:
        probenort.wegraeumen(ordner)


def probe_dubletten() -> None:
    print("\nDubletten - die JUENGERE wird ueberholt, nicht die aeltere")
    fakten = [
        {"id": 10, "text": f"{NAMENS} Tochter heißt Lena Marie.", "quelle": ""},
        {"id": 20, "text": f"Lena Marie ist {NAMENS} Tochter.", "quelle": ""},
        {"id": 30, "text": "Der Drucker steht im Flur.", "quelle": ""},
    ]
    befunde = pruefung.dubletten(fakten)
    pruefe(len(befunde) == 1, "eine Dublette von drei Fakten: %d"
           % len(befunde))
    if befunde:
        pruefe(befunde[0]["alt"] == 10 and befunde[0]["jung"] == 20,
               "die aeltere bleibt, die juengere wird ueberholt: "
               "%s -> %s" % (befunde[0]["jung"], befunde[0]["alt"]))
    pruefe(not pruefung.dubletten([fakten[2]]),
           "ein einzelner Fakt ist keine Dublette")


def probe_mangel_und_zahl() -> None:
    print("\nmangel() nachtraeglich, und die erfundene Zahl")
    wortlaute = {"Sitzung s-1": f"{NAME} fragte nach dem Drucker im Flur."}
    fakten = [
        {"id": 1, "text": "Ich kann den Bildschirm sehen.",
         "quelle": "Sitzung s-1"},
        {"id": 2, "text": "Der Termin ist am 17. um 14:30.",
         "quelle": "Sitzung s-1"},
        {"id": 3, "text": "Der Drucker steht im Flur.",
         "quelle": "Sitzung s-1"},
    ]
    befunde = pruefung.fakten_mit_mangel(fakten, wortlaute)
    arten = {x["art"]: x["id"] for x in befunde}
    pruefe(arten.get("fakt_mangelhaft") == 1,
           "ein Fakt ueber sich selbst faellt auf: %s" % arten)
    pruefe(arten.get("zahl_erfunden") == 2,
           "eine Zahl, die im Wortlaut fehlt, auch: %s" % arten)
    pruefe(3 not in arten.values(),
           "und der saubere Fakt NICHT: %s" % arten)


def probe_verdacht_nur_nutzer() -> None:
    print(f"\nTerminverdacht: nur aus {NAMENS.upper()} Seite (Fehlalarm vom 12.09.)")
    ordner = frisch()
    try:
        sid = sitzung.sitzung_fuer(TAGS, NUTZER)
        # SEIN eigener Satz mit einer Uhrzeit - kein Termin. Genau dieser Satz
        # hat im ersten Trockenlauf einen Fehlalarm erzeugt.
        sitzung.paar_anhaengen(
            sid, None,
            "Ich habe eine neue Datei cpu-z.exe, 4629 KB, am 21:06 Uhr im "
            "Download-Ordner gefunden.", TAGS)
        befunde = pruefung.termin_verdacht(
            sitzung.lesen(), lambda s: sitzung.paare(s), lambda s: False)
        pruefe(befunde == [],
               "seine eigene Ansprache erzeugt keinen Verdacht: %s"
               % [b["text"][:50] for b in befunde])

        # Calvins Satz mit Zeitwort dagegen schon.
        sid2 = sitzung.sitzung_fuer(TAGS + 3600, "handy")
        sitzung.paar_anhaengen(sid2, "Ich muss morgen um zehn zum Arzt.",
                               "Ich merke es mir.", TAGS + 3600)
        befunde = pruefung.termin_verdacht(
            sitzung.lesen(), lambda s: sitzung.paare(s), lambda s: False)
        pruefe(len(befunde) == 1 and befunde[0]["sid"] == sid2,
               f"{NAMENS} Satz mit Zeitwort schon: %s"
               % [(b["sid"], b["text"][:40]) for b in befunde])

        # "gestern" ist KEIN vergessener Termin, sondern keiner.
        sid3 = sitzung.sitzung_fuer(TAGS + 7200, "tablet")
        sitzung.paar_anhaengen(sid3, "Ich war gestern beim Arzt.", "Verstanden.",
                               TAGS + 7200)
        befunde = pruefung.termin_verdacht(
            sitzung.lesen(), lambda s: sitzung.paare(s),
            lambda s: s != sid3)
        pruefe(befunde == [],
               "'Ich war gestern beim Arzt' ist kein Verdacht: %s"
               % [b["text"][:46] for b in befunde])

        # Und existiert ein Termin aus der Sitzung, ist nichts vergessen.
        befunde = pruefung.termin_verdacht(
            sitzung.lesen(), lambda s: sitzung.paare(s), lambda s: True)
        pruefe(befunde == [], "mit Termin kein Verdacht")
    finally:
        probenort.wegraeumen(ordner)


def probe_nicht_zweimal_vorlegen() -> None:
    print("\nB7: derselbe Verdacht kommt NICHT jede Nacht wieder")
    ordner = frisch()
    try:
        sid = sitzung.sitzung_fuer(TAGS, NUTZER)
        sitzung.paar_anhaengen(sid, "Ich muss morgen um zehn zum Arzt.",
                               "Ich merke es mir.", TAGS)
        sitzung.schliessen(sid, TAGS + 11 * MIN)
        sitzung.marke_setzen(sid, "zusammenfassung", "Es ging um den Arzt.")
        sitzung.marke_setzen(sid, "abgeleitet", "trocken: 1")

        zeilen = []
        b1 = pruefung.durchgang(NACHT, scharf=True,
                                journal=lambda k, t, **e: zeilen.append((k, t)))
        pruefe(b1["neu"] >= 1, "erste Nacht: %d neue Befunde" % b1["neu"])
        pruefe(b1["schon_vorgelegt"] == 0, "und keiner lag schon vor")
        pruefe(any(k == "pruefung" for k, _ in zeilen),
               "der Bericht geht ins Journal, mit Zahlen: %s"
               % [t[:60] for k, t in zeilen if k == "pruefung"])

        # Der zweite Lauf muss NOCH IM FENSTER liegen, sonst prueft die Probe
        # das Fenster statt die Marke: Eine Sitzung ausserhalb der 26 Stunden
        # und mit `geprueft` gesetzt wird gar nicht mehr angesehen, und dann
        # ist `neu == 0` richtig, aber kein Beweis.
        b2 = pruefung.durchgang(NACHT + 3600, scharf=True)
        pruefe(b2["geprueft"] >= 1,
               "dieselbe Sitzung wird noch einmal angesehen: %d"
               % b2["geprueft"])
        pruefe(b2["befunde"] >= 1,
               "und der Befund entsteht erneut: %d" % b2["befunde"])
        pruefe(b2["neu"] == 0,
               "aber er gilt NICHT als neu - sonst wird sie abgeschaltet: %d"
               % b2["neu"])
        pruefe(b2["schon_vorgelegt"] >= 1,
               "sondern als 'lag schon vor' gezaehlt: %d"
               % b2["schon_vorgelegt"])
        pruefe(b2["vorzulegen"] == [],
               "und nichts wird noch einmal vorgelegt: %s" % b2["vorzulegen"])

        # Erst wenn sich der GEGENSTAND aendert, kommt ein Befund wieder.
        sitzung.paar_anhaengen(sid, "Und am Freitag um acht noch einmal.",
                               "Auch das merke ich mir.", TAGS + 60)
        b3 = pruefung.durchgang(NACHT + 7200, scharf=True)
        pruefe(b3["neu"] >= 1,
               "ein neues Paar ist ein neuer Gegenstand: %d neu" % b3["neu"])

        # Die Marke haengt am GEGENSTAND, nicht am Wortlaut.
        g = pruefung.gegenstand({"art": "termin_verdacht", "sid": "s-1",
                                 "woran": "paar0", "text": "irgendein Satz"})
        g2 = pruefung.gegenstand({"art": "termin_verdacht", "sid": "s-1",
                                  "woran": "paar0", "text": "anders formuliert"})
        pruefe(g == g2,
               "zweimal derselbe Gegenstand, anderer Wortlaut: gleich (%s)" % g)
    finally:
        probenort.wegraeumen(ordner)


def probe_schliesst_zuerst() -> None:
    print("\nZuerst schliessen, dann pruefen (D.1)")
    ordner = frisch()
    try:
        # Eine Sitzung, die der Faden aus B verpasst hat.
        sid = sitzung.sitzung_fuer(TAGS, NUTZER)
        sitzung.paar_anhaengen(sid, "Frage", "Antwort", TAGS)
        pruefe(sitzung.kopf(sid)["geschlossen"] is None, "sie ist offen")

        b = pruefung.durchgang(NACHT, scharf=False)
        pruefe(b["geschlossen"] == 1,
               "die Nacht schliesst sie nachtraeglich: %d" % b["geschlossen"])
        pruefe(sitzung.kopf(sid)["geschlossen"] is not None,
               "und die Marke steht")
    finally:
        probenort.wegraeumen(ordner)


def probe_trocken_aendert_nichts() -> None:
    print("\nDer Trockenlauf aendert nichts - auch keine Marke")
    ordner = frisch()
    try:
        sid = sitzung.sitzung_fuer(TAGS, NUTZER)
        sitzung.paar_anhaengen(sid, "Ich muss morgen zum Arzt.", "Gut.", TAGS)
        sitzung.schliessen(sid, TAGS + 11 * MIN)
        sitzung.marke_setzen(sid, "zusammenfassung", "Arzt.")
        sitzung.marke_setzen(sid, "abgeleitet", "trocken: 0")

        b = pruefung.durchgang(NACHT, scharf=False)
        pruefe(b["scharf"] is False, "er weiss, dass er trocken laeuft")
        pruefe(not pruefung.ZUSTAND.exists(),
               "kein Zustand geschrieben - sonst gilt der Befund als "
               "vorgelegt, ohne dass ihn jemand gesehen hat")
        pruefe(sitzung.kopf(sid)["geprueft"] is None,
               "und die Marke `geprueft` bleibt null: %r"
               % sitzung.kopf(sid)["geprueft"])

        # Scharf setzt beides.
        pruefung.durchgang(NACHT, scharf=True)
        pruefe(pruefung.ZUSTAND.exists(), "scharf schreibt den Zustand")
        pruefe(sitzung.kopf(sid)["geprueft"] is not None,
               "und setzt `geprueft`")
    finally:
        probenort.wegraeumen(ordner)


def probe_fenster_und_deckel() -> None:
    print("\nDas Fenster: 26 Stunden ODER geprueft=null, mit Deckel (B8)")
    ordner = frisch()
    try:
        # Eine alte, nie geprueft - sie darf NICHT herausfallen.
        alt = sitzung.sitzung_fuer(TAGS - 5 * 24 * 3600, NUTZER)
        sitzung.paar_anhaengen(alt, "Alte Frage", "Alte Antwort",
                               TAGS - 5 * 24 * 3600)
        sitzung.schliessen(alt, TAGS - 5 * 24 * 3600 + 600)
        # Eine alte, schon geprueft - die schon.
        alt2 = sitzung.sitzung_fuer(TAGS - 4 * 24 * 3600, "handy")
        sitzung.paar_anhaengen(alt2, "Frage", "Antwort", TAGS - 4 * 24 * 3600)
        sitzung.schliessen(alt2, TAGS - 4 * 24 * 3600 + 600)
        sitzung.marke_setzen(alt2, "geprueft", TAGS)

        koepfe, rueckstand = pruefung._sitzungen_im_fenster(NACHT, 12)
        ids = [k["id"] for k in koepfe]
        pruefe(alt in ids,
               "die alte mit geprueft=null bleibt dran - sonst faellt sie FUER "
               "IMMER heraus: %s" % ids)
        pruefe(alt2 not in ids,
               "die alte, schon geprueft, nicht mehr: %s" % ids)

        # Der Deckel, und der Rueckstand wird GENANNT.
        for i in range(6):
            s = sitzung.sitzung_fuer(TAGS - (10 + i) * 3600, "gerät%d" % i)
            sitzung.paar_anhaengen(s, "F", "A", TAGS - (10 + i) * 3600)
            sitzung.schliessen(s, TAGS - (10 + i) * 3600 + 600)
        koepfe, rueckstand = pruefung._sitzungen_im_fenster(NACHT, 3)
        pruefe(len(koepfe) == 3, "hoechstens drei: %d" % len(koepfe))
        pruefe(rueckstand > 0,
               "und der Rueckstand wird gezaehlt, nicht verschwiegen: %d"
               % rueckstand)
        b = pruefung.durchgang(NACHT, scharf=False, deckel=3)
        pruefe(b["rueckstand"] == rueckstand,
               "er steht im Bericht: %d" % b["rueckstand"])
    finally:
        probenort.wegraeumen(ordner)


def main() -> int:
    probe_faellig()
    probe_liegengeblieben()
    probe_dubletten()
    probe_mangel_und_zahl()
    probe_verdacht_nur_nutzer()
    probe_nicht_zweimal_vorlegen()
    probe_schliesst_zuerst()
    probe_trocken_aendert_nichts()
    probe_fenster_und_deckel()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
