"""Probe fuer nacht.py - die Nacht als Auskunft, nicht als Ausdruck.

    python -X utf8 nacht_test.py

nacht.py war bis zum 13.09. ein Ausdruck fuer Calvin und sonst nichts: `main()`
schrieb direkt nach stdout, und niemand sonst konnte die Auswahl lesen. Genau
deshalb gab es zwei Begriffe von "wichtig" im System - hier standen Pruefung,
Trockenlauf und Zusammenfassungen, und passiert.py beantwortete DIESELBE Nacht
mit zwoelf Dateiaenderungen und einem Bedarfsdienst.

Gemessen wird daher beides:
  gruppen()     die Auswahl, fuer sich pruefbar
  fuer_prompt() derselbe Inhalt in einem Block, den ein Prompt tragen kann
  ARTEN         und dass passiert.py fuer jede davon ein Gewicht hat

Alles gegen ein FESTES Jetzt: Sonntag, 13.09.2026, 04:00. Eine Probe, die
`time.time()` benutzt, misst die Uhr mit.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS, NUTZER
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
import nacht

GESAMT = 0
FEHLER = 0
JETZT = datetime(2026, 9, 13, 4, 0).timestamp()
H = 3600.0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


# Eine Nacht, wie sie am 13.09. wirklich im Journal stand - die wichtigen
# Zeilen zwischen dem Rauschen, das sie damals verdraengt hat.
NACHT = [
    (JETZT - 6 * H, "fund", "Die Datei beschreibungen.json wurde geaendert."),
    (JETZT - 6 * H, "haus", "MoNotificationUx kommt und geht von selbst."),
    (JETZT - 5.5 * H, "sitzung", "Es ging um Spielarten und den Desktop"),
    (JETZT - 5 * H, "sitzung", "Es ging um den freien Speicher"),
    (JETZT - 4.5 * H, "ableiten_trocken",
     "WUERDE anlegen - fakt: 916 MB sind ungefaehr 0,92 GB."),
    (JETZT - 4.4 * H, "ableiten_zurueck", "zurueckgehalten: zu unsicher"),
    (JETZT - 4 * H, "kernwissen_fehlt",
     "ERINNERUNG.md fehlt - das Kernwissen geht in keinen Prompt mehr mit."),
    (JETZT - 3 * H, "verlust",
     "Es fehlen: ERINNERUNG.md, erinnerungen.json. Nachgebaut ist nichts."),
    (JETZT - 2 * H, "fehler", "Faden ansprache abgestuerzt"),
    # ZWEI Pruefungen, wie in der Nacht vom 13.09. (23:40 und 02:03) - mit nur
    # einer faellt nicht auf, wenn der Block die Anzahl statt der Zeiten nennt.
    (JETZT - 4.2 * H, "pruefung",
     "4 Sitzungen geprueft, 3 neue Befunde"),
    (JETZT - 2 * H, "pruefung",
     "4 Sitzungen geprueft, 0 nachtraeglich geschlossen, 0 neue Befunde"),
    (JETZT - 1.9 * H, "vorgelegt", "Eine Sitzung blieb ohne Zusammenfassung"),
    (JETZT - 1.8 * H, "rueckfrage", "Darf ABLEITEN_SCHARF gesetzt werden?"),
    # Muss DRAUSSEN bleiben: vor dem Fenster.
    (JETZT - 20 * H, "pruefung", "die Pruefung der VORNACHT"),
]


def journal(zeilen) -> Path:
    """Ein Journal aus (ts, kind, text) oder (ts, kind, text, extra)."""
    ordner = Path(tempfile.mkdtemp(prefix="nacht_probe_"))
    pfad = ordner / "journal.jsonl"
    satz = []
    for z in zeilen:
        ts, kind, text = z[0], z[1], z[2]
        e = {"ts": ts, "kind": kind, "text": text}
        if len(z) > 3:
            e.update(z[3])
        satz.append(json.dumps(e, ensure_ascii=False) + "\n")
    pfad.write_text("".join(satz), encoding="utf-8")
    nacht.JOURNAL = pfad
    return pfad


# Was an MIR gearbeitet wurde: die vier Fragen aus zuhause_probe.py, als
# Sitzung zusammengefasst. Am 13.09. erzaehlte er sie Calvin als seine Nacht.
AN_MIR = [
    (JETZT - 5.2 * H, "sitzung",
     "Diskussion behandelte Spielarten und Inhalt des Desktops",
     {"von": "test"}),
    (JETZT - 5.1 * H, "ableiten_trocken",
     "WUERDE anlegen - fakt: 916 MB sind ungefaehr 0,92 GB.",
     {"von": "test"}),
]


def probe_testfragen_sind_keine_nacht() -> None:
    """Eine Testfrage ist kein Ereignis - genauso wenig wie eine Erinnerung.

    Der Befund vom 13.09., 04:22: "22 30 Uhr diskutierte man ueber Spielarten
    und Desktop" - das waren zuhause_probe.py's vier Fragen, in deren
    Reihenfolge. Calvin hat nie darueber geredet und haette eine fremde
    Geschichte als seine gehoert.
    """
    print(f"\neine Testfrage ist kein Ereignis in {NAMENS} Nacht")
    journal(NACHT + AN_MIR)
    seine, an_mir = nacht.geteilt(stunden=12.0, jetzt=JETZT)

    pruefe(len(an_mir["sitzung"]) == 1 and len(seine["sitzung"]) == 2,
           "die Messsitzung liegt auf der anderen Seite: seine %d, an mir %d"
           % (len(seine["sitzung"]), len(an_mir["sitzung"])))
    # Auf den SATZ pruefen, nicht auf das Wort: "Spielarten" steht auch in
    # einer echten Sitzung dieser Nacht, und darum soll es ja gerade gehen -
    # dasselbe Thema, zwei verschiedene Herkuenfte.
    pruefe(all(AN_MIR[0][2] not in str(e.get("text"))
               for e in seine["sitzung"]),
           "und steht nicht mehr unter seinen Gespraechen")

    b = nacht.fuer_prompt(stunden=12.0, jetzt=JETZT)
    pruefe("Spielarten und Inhalt des Desktops" not in b,
           "sie wird ihm nicht mehr erzaehlt")
    # Verschwiegen wird sie aber auch nicht - das waere derselbe Fehler
    # andersherum: "nichts passiert" bei einer Nacht voller Messungen.
    pruefe("an mir gearbeitet" in b and "2 Zeilen" in b,
           "sie wird gezaehlt und benannt: %s"
           % [zeile for zeile in b.splitlines() if "an mir" in zeile])


def probe_nur_an_mir_gearbeitet() -> None:
    """Bestand die Nacht NUR aus Messungen, ist die ehrliche Antwort weder
    "nichts passiert" noch eine Erzaehlung daraus."""
    print("\neine Nacht, die nur aus Messungen bestand")
    journal(AN_MIR)
    b = nacht.fuer_prompt(stunden=12.0, jetzt=JETZT)
    pruefe(f"nichts passiert, was {NAME} betrifft" in b,
           "er sagt, dass ihn nichts davon betrifft")
    pruefe("an MIR gearbeitet" in b,
           "und sagt, was stattdessen war")
    pruefe("Spielarten" not in b and "0,92 GB" not in b,
           "ohne die Messungen als Geschichte zu erzaehlen")
    pruefe("NICHT gelaufen" not in b,
           "und ohne die fehlende Pruefung zu beklagen - es war keine Nacht, "
           "in der etwas haette laufen sollen")


def probe_fehlendes_feld_ist_vom_nutzer() -> None:
    """Ein fehlendes Feld ist kein leeres Ergebnis.

    Alle Zeilen vor dem 13.09. tragen kein `von`. Sie als "nicht Calvins"
    wegzuwerfen hiesse, eine echte Nacht zu verschweigen, um eine falsche zu
    verhindern.
    """
    print(f"\nein fehlendes von gilt als {NAMENS} - nicht als Test")
    journal(NACHT)
    seine, an_mir = nacht.geteilt(stunden=12.0, jetzt=JETZT)
    pruefe(not any(an_mir.values()),
           "keine Zeile ohne Absender landet auf der Testseite")
    pruefe(len(seine["sitzung"]) == 2,
           "und seine zwei Gespraeche bleiben seine")

    import passiert
    pruefe(passiert.ist_vom_nutzer({}) is True,
           f"ohne Feld: {NAMENS}")
    pruefe(passiert.ist_vom_nutzer({"von": NUTZER}) is True,
           f"von {NUTZER}: {NAMENS}")
    pruefe(passiert.ist_vom_nutzer({"von": "test"}) is False,
           f"von test: nicht {NAMENS}")
    pruefe(passiert.ist_vom_nutzer({"von": "TEST"}) is False,
           "und die Schreibweise ist egal")


def probe_gruppen() -> None:
    print("\ngruppen() - die Auswahl, fuer sich pruefbar")
    journal(NACHT)
    g = nacht.gruppen(stunden=12.0, jetzt=JETZT)

    pruefe(set(g) == set(nacht.ARTEN),
           "jede Art aus ARTEN kommt vor, auch die leeren - "
           "\"die Pruefung ist nicht gelaufen\" ist eine Auskunft")
    pruefe(len(g["sitzung"]) == 2, "zwei zusammengefasste Gespraeche: %d"
           % len(g["sitzung"]))
    pruefe(len(g["ableiten_trocken"]) == 1, "ein Satz aus dem Trockenlauf")
    pruefe(len(g["pruefung"]) == 2,
           "die Pruefung der VORNACHT liegt vor dem Fenster und zaehlt "
           "nicht mit: %d" % len(g["pruefung"]))
    pruefe("fund" not in g and "haus" not in g,
           "Dateiaenderungen und Bedarfsdienste sind keine Nachtauskunft")

    leer = nacht.gruppen(stunden=0.01, jetzt=JETZT)
    pruefe(set(leer) == set(nacht.ARTEN) and not any(leer.values()),
           "eine leere Nacht gibt alle Arten leer zurueck, nicht {}")


def probe_fuer_prompt() -> None:
    """Die vier Dinge, die am 13.09. in der Antwort fehlten, stehen drin."""
    print("\nfuer_prompt() - was am 13.09. fehlte, steht jetzt darin")
    journal(NACHT)
    b = nacht.fuer_prompt(stunden=12.0, jetzt=JETZT)

    pruefe("Gegenpruefung" in b and "4 Sitzungen geprueft" in b,
           "die Gegenpruefung steht darin")
    # Die Zeiten ALLE, nicht die Anzahl. Aus "lief 2 Mal, zuletzt 02:03"
    # machte gpt-oss "zwei Ueberpruefungen um 02:03" - gemessen am 13.09.
    # Eine Zahl neben einer Uhrzeit wird zu einer Zahl VON Uhrzeiten.
    zeiten = [nacht._uhr(e) for e in nacht.gruppen(12.0, JETZT)["pruefung"]]
    pruefe(all(t in b for t in zeiten),
           "jede Pruefungszeit steht einzeln darin (%s) - nicht die Anzahl"
           % ", ".join(zeiten))
    pruefe("2 Mal" not in b,
           "und nirgends eine Anzahl neben einer Uhrzeit")
    pruefe("2 Gespraeche" in b and "freien Speicher" in b,
           "die zusammengefassten Gespraeche stehen darin")
    pruefe("Trockenlauf" in b and "0,92 GB" in b,
           "der Trockenlauf steht darin, mit dem Satz")
    pruefe("ERINNERUNG.md" in b,
           "der Verlust der Werkstatt steht darin - er gilt weiter")
    pruefe("Kernwissen" in b,
           "und dass das Kernwissen in keinen Prompt mehr mitgeht")
    pruefe("Darf ABLEITEN_SCHARF" in b,
           "worauf er eine Antwort braucht, steht darin")

    # Das Gegenteil ist genauso wichtig: Das Rauschen, das die Antwort am
    # 13.09. AUSGEMACHT hat, darf nicht mehr vorkommen.
    pruefe("beschreibungen.json" not in b,
           "eine geaenderte JSON-Datei kommt NICHT mehr vor")
    pruefe("MoNotificationUx" not in b,
           "ein Bedarfsdienst kommt NICHT mehr vor")

    pruefe("WUERDE anlegen" not in b,
           "die Marke \"WUERDE anlegen\" ist abgeschnitten - sie ist fuer "
           "den Ausdruck, nicht zum Vorlesen")
    pruefe(len(nacht.fuer_prompt(stunden=12.0, jetzt=JETZT,
                                 hoechstens=200)) <= 200,
           "der Block haelt seine Obergrenze - ein Prompt hat ein Mass")

    # Eine Nacht ohne Pruefung: Das ist selbst der erste Befund, und er darf
    # nicht als Schweigen durchgehen.
    journal([z for z in NACHT if z[1] != "pruefung"])
    ohne = nacht.fuer_prompt(stunden=12.0, jetzt=JETZT)
    pruefe("NICHT gelaufen" in ohne,
           "eine nicht gelaufene Pruefung wird gesagt, nicht verschwiegen")

    journal([])
    pruefe("NICHT gelaufen" in nacht.fuer_prompt(stunden=12.0, jetzt=JETZT),
           "und ein leeres Journal erfindet keine Nacht")


def probe_ein_begriff_von_wichtig() -> None:
    print("\nein Begriff von \"wichtig\", nicht zwei")
    import passiert
    fehlend = [a for a in nacht.ARTEN if a not in passiert.GEWICHT]
    pruefe(not fehlend,
           "passiert.py hat fuer jede Art aus ARTEN ein Gewicht: fehlt %s"
           % (fehlend or "keine"))
    zu_leicht = [a for a in nacht.ARTEN
                 if passiert.GEWICHT.get(a, 0) <= passiert.GEWICHT_UNBEKANNT]
    pruefe(not zu_leicht,
           "und keine davon liegt noch auf dem stummen Ruecklagenwert "
           "von %d: %s" % (passiert.GEWICHT_UNBEKANNT, zu_leicht or "keine"))


def probe_bericht_laeuft_noch() -> None:
    """main() schreibt weiter denselben Ausdruck - gruppen() hat ihn nur
    woanders hergeholt."""
    print(f"\nder Ausdruck fuer {NAME} laeuft weiter")
    journal(NACHT)
    import io
    import contextlib
    puffer = io.StringIO()
    alt = sys.argv
    sys.argv = ["nacht.py"]
    try:
        with contextlib.redirect_stdout(puffer):
            rc = nacht.main()
    finally:
        sys.argv = alt
    raus = puffer.getvalue()
    pruefe(rc == 0, "er laeuft durch")
    pruefe("DIE NACHT" in raus, "und hat seine Ueberschrift")
    pruefe("WAS C ANGELEGT HAETTE" in raus,
           f"und den Abschnitt, an dem {NAME} ueber ABLEITEN_SCHARF entscheidet")


def main() -> int:
    echt = nacht.JOURNAL
    try:
        probe_gruppen()
        probe_fuer_prompt()
        probe_testfragen_sind_keine_nacht()
        probe_nur_an_mir_gearbeitet()
        probe_fehlendes_feld_ist_vom_nutzer()
        probe_ein_begriff_von_wichtig()
        probe_bericht_laeuft_noch()
    finally:
        nacht.JOURNAL = echt
    print("\n%d von %d bestanden" % (GESAMT - FEHLER, GESAMT))
    print("das echte Journal (%s) wurde nicht angefasst" % echt.name)
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
