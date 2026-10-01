"""Probe fuer sitzung.py - Schritt A.

    python sitzung_test.py

Alles gegen ein FESTES Jetzt: Samstag, 12.09.2026, 14:00. Eine Probe, die
`time.time()` benutzt, misst die Uhr mit und fehlt irgendwann nachts um halb
drei, ohne dass jemand weiss, warum.

Keine Datei der Werkstatt wird angefasst. Die Probe legt sich einen eigenen
Ordner an - nicht unter `werkstatt/`, denn dort waere sie eine "Veraenderung
der Lage" und der Bewohner wuerde ueber seine eigene Probe nachdenken.

Geprueft wird, was der Plan unter "Proben, je Schritt eine" fuer A verlangt:
Zuordnung, Ruhe, Obergrenze, Neustart mit offener Sitzung, Anschluss nach
zwanzig Minuten - dazu aus B5 bis B9 und B11: `von == "test"` bekommt keine
Sitzung, zwei Absender werden nicht vermischt, Reinrutschen schliesst die
offene, eine Ansprache eroeffnet eine Sitzung mit `frage: null`, und bei
mehreren faelligen kommt EINE.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS, NUTZER
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import probenort
import sitzung

GESAMT = 0
FEHLER = 0

# Samstag, 12.09.2026, 14:00 - dasselbe Jetzt wie in Anhang 2.
JETZT_D = datetime(2026, 9, 12, 14, 0)
JETZT = JETZT_D.timestamp()
MIN = 60.0
STD = 3600.0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def frisch() -> Path:
    """Ein leerer Bestand. sitzung.py haelt keinen Zustand im Speicher, nur
    die zwei Pfade - also reicht es, die umzubiegen."""
    ordner = probenort.ablage("sitzung")
    sitzung.WERKSTATT = ordner
    sitzung.KOEPFE = ordner / "sitzungen.jsonl"
    sitzung.ORDNER = ordner / "sitzungen"
    return ordner


def wegraeumen() -> None:
    """Raeumt den Probenordner weg - und NUR den.

    Der Riegel dagegen steht in probe.py, an der Stelle, die loescht - nicht
    hier. Hier stand er vorher, und genau das war zu wenig: Jede andere Probe
    konnte denselben Fehler wieder machen. Am 12.09. gegen 21:00 hat er 131
    Erinnerungen, die Chronik und die Termine gekostet.
    """
    probenort.wegraeumen(sitzung.WERKSTATT)


def fragen(ts: float, text: str, von: str = NUTZER,
           gewuenscht: str | None = None) -> str | None:
    """Eine Frage stellen und beantworten, wie gespraech.py es tut: zuordnen,
    wenn die Antwort steht das Paar anhaengen."""
    sid = sitzung.sitzung_fuer(ts, von, gewuenscht)
    sitzung.paar_anhaengen(sid, text, "Antwort auf: %s" % text, ts)
    return sid


# ------------------------------------------------------------------ Proben


def probe_zuordnung() -> None:
    print("\nZuordnung: was zusammengehoert, bleibt zusammen (A.5)")
    frisch()
    a = fragen(JETZT, "Wer belegt den meisten Speicher?")
    b = fragen(JETZT + 2 * MIN, "Und wie viel ist das in Gigabyte?")
    c = fragen(JETZT + 9 * MIN, "Laeuft das schon lange?")
    pruefe(a == b == c, "drei Fragen in neun Minuten sind EINE Sitzung: %s" % a)

    k = sitzung.kopf(a)
    pruefe(k["paare"] == 3, "drei Paare im Kopf: %s" % k["paare"])
    pruefe(k["letzte_frage"] == JETZT + 9 * MIN, "letzte_frage rueckt nach")
    pruefe(k["von"] == NUTZER and k["fortsetzung_von"] is None,
           "Absender steht drin, kein Anschluss")
    pruefe(all(k[m] is None for m in ("geschlossen", "zusammenfassung",
                                      "abgeleitet", "geprueft")),
           "alle vier Marken stehen auf null (A.4)")

    p = sitzung.paare(a)
    pruefe(len(p) == 3 and p[0]["frage"].startswith("Wer belegt"),
           "der Wortlaut liegt in der Reihenfolge vor")
    pruefe(sitzung.paare(a, letzte=2) == p[-2:],
           "letzte=2 gibt die letzten zwei")
    pruefe(sitzung.paare("s-gibtsnicht") == [],
           "eine Sitzung ohne Wortlaut ist kein Fehler")


def probe_ruhe() -> None:
    print("\nRuhe: nach zehn Minuten Schweigen ist sie zu Ende (A.1)")
    frisch()
    a = fragen(JETZT, "Was machen wir am Wochenende?")
    b = fragen(JETZT + 11 * MIN, "Und was war mit dem anderen Punkt?")
    pruefe(a != b, "elf Minuten spaeter ist eine neue Sitzung")
    pruefe(sitzung.kopf(b)["fortsetzung_von"] == a,
           "sie verweist auf die alte (A.3): %s"
           % sitzung.kopf(b)["fortsetzung_von"])
    pruefe(sitzung.kopf(a)["geschlossen"] == JETZT + 11 * MIN,
           "die alte ist dabei geschlossen worden - nicht zwei offene")

    # Genau auf der Grenze: 10 Minuten sind vorbei, 9:59 nicht.
    frisch()
    a = fragen(JETZT, "eins")
    pruefe(fragen(JETZT + 10 * MIN - 1, "zwei") == a, "9:59 faellt noch hinein")
    frisch()
    a = fragen(JETZT, "eins")
    pruefe(fragen(JETZT + 10 * MIN, "zwei") != a, "10:00 nicht mehr")


def probe_anschluss() -> None:
    print("\nAnschluss: bis 90 Minuten ein Verweis, danach ein neues Gespraech")
    frisch()
    a = fragen(JETZT, "Wie war das mit dem Kinderarzt?")
    b = fragen(JETZT + 20 * MIN, "Und die Unterlagen?")
    pruefe(sitzung.kopf(b)["fortsetzung_von"] == a,
           "nach 20 Minuten: Verweis")

    c = fragen(JETZT + 20 * MIN + 100 * MIN, "Ganz anderes Thema.")
    pruefe(sitzung.kopf(c)["fortsetzung_von"] is None,
           "100 Minuten nach der letzten Frage: kein Verweis mehr")

    # Die Kette: b verweist auf a, und c faengt neu an. Sonst koennte das
    # Reinrutschen keiner Kette folgen.
    pruefe(sitzung.kopf(a)["fortsetzung_von"] is None
           and sitzung.kopf(b)["fortsetzung_von"] == a,
           "die Kette zeigt nach hinten, nicht nach vorn")


def probe_obergrenze() -> None:
    print("\nObergrenze: sechs Stunden, dann eine Nachfolgerin (A.1)")
    frisch()
    a = fragen(JETZT, "Fang an.")
    # Alle fuenf Minuten eine Frage, sieben Stunden lang: ohne Obergrenze
    # waere das EINE Sitzung, und ihre Zusammenfassung waere keine mehr.
    sid = a
    ts = JETZT
    wechsel = None
    for i in range(1, 85):
        ts = JETZT + i * 5 * MIN
        neu = fragen(ts, "Frage %d" % i)
        if neu != sid and wechsel is None:
            wechsel = (sid, neu, ts)
        sid = neu
    pruefe(wechsel is not None, "irgendwann wird geschnitten")
    if wechsel:
        alt, neu, ts_w = wechsel
        pruefe(abs(ts_w - (JETZT + 6 * STD)) <= 5 * MIN,
               "und zwar bei sechs Stunden: %s"
               % datetime.fromtimestamp(ts_w).strftime("%H:%M"))
        pruefe(sitzung.kopf(alt)["geschlossen"] == ts_w,
               "die alte wird geschlossen")
        pruefe(sitzung.kopf(neu)["fortsetzung_von"] == alt,
               "die neue traegt fortsetzung_von")
    pruefe(len(sitzung._offen_alle()) == 1,
           "und nie mehr als eine offene: %d" % len(sitzung._offen_alle()))


def probe_test_bekommt_keine() -> None:
    print("\nRegel 0: von == \"test\" bekommt keine Sitzung (B6)")
    frisch()
    pruefe(sitzung.sitzung_fuer(JETZT, "test") is None, "sitzung_fuer -> None")
    pruefe(sitzung.sitzung_fuer(JETZT, "TEST") is None,
           "auch gross geschrieben")
    for i in range(12):
        fragen(JETZT + i, "Testfrage %d" % i, von="test")
    pruefe(sitzung.lesen() == [],
           "zwoelf Testfragen hinterlassen keinen einzigen Kopf")
    pruefe(not (Path(sitzung.ORDNER).exists()
                and any(Path(sitzung.ORDNER).iterdir())),
           "und keinen Wortlaut")


def probe_zwei_absender() -> None:
    print("\nZwei Absender werden nicht vermischt (Anhang 3)")
    frisch()
    a = fragen(JETZT, f"Frage von {NAME}", von=NUTZER)
    b = fragen(JETZT + 30, "Frage vom Handy", von="handy")
    pruefe(a != b, "zwei Absender, zwei Sitzungen")
    pruefe(sitzung.kopf(a)["paare"] == 1 and sitzung.kopf(b)["paare"] == 1,
           "je ein Paar, nichts vermischt")
    pruefe(fragen(JETZT + 60, "noch eine", von=NUTZER) == a,
           f"die zweite von {NAME} faellt in {NAMENS} Sitzung")
    pruefe(len(sitzung.offene(JETZT + 60, NUTZER)) == 1,
           "offene(von) sieht nur den eigenen Absender")
    # Gleiche Sekunde, zwei Absender: zwei Kennungen, nicht eine.
    frisch()
    x = fragen(JETZT, "a", von=NUTZER)
    y = fragen(JETZT, "b", von="handy")
    pruefe(x != y, "gleiche Sekunde, verschiedene Kennung: %s / %s" % (x, y))


def probe_reinrutschen() -> None:
    print("\nReinrutschen: die offene wird geschlossen (B5), dieselbe wieder auf")
    frisch()
    alt = fragen(JETZT, "Ueber den Kinderarzt.")
    # Zwei Tage spaeter ein anderes Thema - und dann zurueck in das alte.
    spaeter = JETZT + 2 * 24 * STD
    neu = fragen(spaeter, "Was laeuft gerade?")
    pruefe(alt != neu, "zwei Tage spaeter ist es nicht dieselbe")

    zurueck = fragen(spaeter + MIN, "Und was sagte der Arzt?", gewuenscht=alt)
    pruefe(zurueck == alt, "mit Feld `sitzung` geht es in die alte zurueck")
    pruefe(sitzung.kopf(neu)["geschlossen"] == spaeter + MIN,
           "die aktuelle ist dabei geschlossen - er hat ja gewechselt")
    pruefe(len(sitzung._offen_alle(NUTZER)) == 1,
           "genau eine offene je Absender, nie zwei")
    k = sitzung.kopf(alt)
    pruefe(k["geschlossen"] is None and k["paare"] == 2,
           "die alte ist wieder offen und hat das neue Paar")

    # Eine Kennung, die es nicht gibt, darf nicht in die Leere zeigen.
    frisch()
    a = fragen(JETZT, "eins")
    pruefe(fragen(JETZT + MIN, "zwei", gewuenscht="s-erfunden") == a,
           "eine unbekannte Kennung wird uebergangen, nicht angelegt")


def probe_wieder_aufnehmen() -> None:
    print("\nWieder aufnehmen: Zusammenfassung bleibt, Arbeitsmarken fallen (A.6)")
    frisch()
    a = fragen(JETZT, "Ueber Lenas Termin.")
    sitzung.schliessen(a, JETZT + 11 * MIN)
    sitzung.marke_setzen(a, "zusammenfassung", "Es ging um Lenas Arzttermin.")
    sitzung.marke_setzen(a, "abgeleitet", JETZT + 12 * MIN)
    sitzung.marke_setzen(a, "geprueft", JETZT + 13 * MIN)

    k = sitzung.wieder_aufnehmen(a, JETZT + 3 * 24 * STD)
    pruefe(k["geschlossen"] is None, "sie ist wieder offen")
    pruefe(k["zusammenfassung"] == "Es ging um Lenas Arzttermin.",
           "die Zusammenfassung steht noch - korrigieren statt loeschen")
    pruefe(k["abgeleitet"] is None and k["geprueft"] is None,
           "abgeleitet und geprueft sind weg: es kommt Neues dazu")
    pruefe(sitzung.paare(a), "der Wortlaut ist nach drei Tagen noch da")

    try:
        sitzung.marke_setzen(a, "zusamenfassung", "x")
        pruefe(False, "ein Tippfehler in der Marke fliegt auf")
    except ValueError:
        pruefe(True, "ein Tippfehler in der Marke fliegt auf")


def probe_faellig_und_neustart() -> None:
    print("\nNeustart und Abschluss: faellig() gibt EINE, die aelteste (B11, B.2)")
    frisch()
    # Drei Gespraeche am Vormittag, der Bewohner war aus. Nichts ist
    # geschlossen - genau die Lage nach einem Ausfall.
    a = fragen(JETZT - 5 * STD, "erstes Gespraech", von=NUTZER)
    b = fragen(JETZT - 4 * STD, "zweites", von="handy")
    c = fragen(JETZT - 3 * STD, "drittes", von="mac")
    pruefe(len(sitzung._offen_alle()) == 3, "drei offene nach dem Ausfall")

    f1 = sitzung.faellig(JETZT)
    pruefe(f1 and f1["id"] == a, "die aelteste zuerst: %s" % (f1 or {}).get("id"))
    sitzung.schliessen(a, JETZT)
    f2 = sitzung.faellig(JETZT)
    pruefe(f2 and f2["id"] == b, "danach die naechste, eine je Durchlauf")
    sitzung.schliessen(b, JETZT)
    sitzung.schliessen(c, JETZT)
    pruefe(sitzung.faellig(JETZT) is None, "dann ist keine mehr faellig")

    # Die Ausnahme aus B.2: frisch bleibt offen. Calvin hat vielleicht nur
    # einen Neustart angestossen und redet gleich weiter.
    frisch()
    d = fragen(JETZT - 2 * MIN, "gerade eben gefragt")
    pruefe(sitzung.faellig(JETZT) is None,
           "eine Sitzung von vor zwei Minuten wird beim Start NICHT geschlossen")
    pruefe(fragen(JETZT, "weiter gehts") == d,
           f"und {NAME} redet in derselben Sitzung weiter (A.2)")

    # Sechs Stunden Dauer macht faellig, auch wenn gerade gefragt wurde.
    frisch()
    e = sitzung.sitzung_fuer(JETZT - 7 * STD, NUTZER)
    sitzung.paar_anhaengen(e, "alt", "alt", JETZT - 7 * STD)
    sitzung._aendern(e, lambda k: k.__setitem__("letzte_frage", JETZT - 30))
    f = sitzung.faellig(JETZT)
    pruefe(f and f["id"] == e, "ueber der Obergrenze ist faellig, auch frisch")

    # Zweimal schliessen aendert den Zeitpunkt nicht - die Marke ist der
    # Anspruch, und zwei Faeden duerfen nicht zweimal zusammenfassen.
    frisch()
    g = fragen(JETZT, "eins")
    sitzung.schliessen(g, JETZT + 11 * MIN)
    sitzung.schliessen(g, JETZT + 20 * MIN)
    pruefe(sitzung.kopf(g)["geschlossen"] == JETZT + 11 * MIN,
           "der erste Abschluss gilt (Anhang 3)")


def probe_ansprache() -> None:
    print("\nWenn ER anfaengt: die Ansprache eroeffnet die Sitzung (B9)")
    frisch()
    sid = sitzung.ansprache_eroeffnet(
        "Die Bruecke ist seit zehn Minuten weg.", JETZT)
    p = sitzung.paare(sid)
    pruefe(len(p) == 1 and p[0]["frage"] is None,
           "erstes Paar mit frage: null")
    pruefe(p[0]["antwort"].startswith("Die Bruecke"),
           "der Anlass steht als Antwort drin")
    pruefe(sitzung.kopf(sid)["paare"] == 1, "und im Kopf gezaehlt")

    # Antwortet Calvin, faellt seine Antwort nach Regel 2 hinein.
    pruefe(fragen(JETZT + 3 * MIN, "Was heisst das?") == sid,
           f"{NAMENS} Antwort faellt in dieselbe Sitzung")
    pruefe(sitzung.kopf(sid)["paare"] == 2, "jetzt zwei Paare")

    # Antwortet er NIE, traegt die Sitzung trotzdem den Anlass.
    frisch()
    sid = sitzung.ansprache_eroeffnet("Der Platz wird knapp.", JETZT)
    pruefe(sitzung.faellig(JETZT + 11 * MIN)["id"] == sid
           and sitzung.paare(sid)[0]["antwort"] == "Der Platz wird knapp.",
           "ohne Antwort wird sie faellig und traegt den Anlass")

    # Mitten im Gespraech eroeffnet sie nichts Neues - eine offene je Absender.
    frisch()
    a = fragen(JETZT, "Wie ist die Lage?")
    pruefe(sitzung.ansprache_eroeffnet("Noch etwas: Ollama ist wieder da.",
                                       JETZT + 2 * MIN) == a,
           "waehrend des Gespraechs gehoert sie in dieses Gespraech")


def probe_finden() -> None:
    print("\nFinden: nach Thema und nach Datum (A.6 Punkt 2)")
    frisch()
    a = fragen(JETZT - 24 * STD, "Wann ist Lena beim Kinderarzt?")
    sitzung.schliessen(a, JETZT - 23 * STD)
    sitzung.marke_setzen(
        a, "zusammenfassung",
        "Es ging um Lenas Termin beim Kinderarzt und um die Unterlagen.")
    b = fragen(JETZT, "Wie viel Platz ist frei?")
    sitzung.marke_setzen(b, "zusammenfassung", "Es ging um den freien Platz.")

    t = sitzung.suchen("Kinderarzt")
    pruefe(len(t) == 1 and t[0]["id"] == a,
           "\"Was war das mit dem Kinderarzt?\" findet genau die eine")
    pruefe(sitzung.suchen("Schnurpsel") == [],
           "und erfindet nichts, wenn nichts passt")
    pruefe(sitzung.suchen("")[:1] == [], "ohne Begriff kein Treffer")

    gestern = (JETZT_D - timedelta(days=1)).date()
    pruefe([k["id"] for k in sitzung.am_tag(gestern)] == [a],
           "\"Worueber haben wir gestern geredet?\" findet sie nach Datum")
    pruefe([k["id"] for k in sitzung.am_tag(JETZT_D.date())] == [b],
           "und heute die heutige")
    pruefe([k["id"] for k in sitzung.am_tag("2026-09-11")] == [a],
           "das Datum geht auch als Text")
    pruefe(sitzung.am_tag("2026-09-10") == [], "ein stiller Tag ist leer")


def probe_platte() -> None:
    print("\nAuf der Platte: kaputte Zeile, halbe Datei, Neustart")
    ordner = frisch()
    a = fragen(JETZT, "eins")
    b = fragen(JETZT + 20 * MIN, "zwei")

    # Eine halb geschriebene Zeile darf nicht den ganzen Bestand kosten.
    with sitzung.KOEPFE.open("a", encoding="utf-8") as f:
        f.write('{"id": "s-kaputt", "begonn\n')
    ids = [k["id"] for k in sitzung.lesen()]
    pruefe(ids == [a, b], "die kaputte Zeile wird uebersprungen: %s" % ids)
    pruefe(fragen(JETZT + 21 * MIN, "drei") == b,
           "und die Zuordnung arbeitet weiter")

    # Ein "Neustart": nichts im Speicher, alles aus der Datei.
    pruefe(sitzung.kopf(b)["paare"] == 2 and len(sitzung.paare(b)) == 2,
           "Kopf und Wortlaut stimmen nach dem Lesen von der Platte ueberein")
    roh = json.loads((ordner / "sitzungen" / ("%s.json" % b)).read_text(
        encoding="utf-8"))
    pruefe(roh["id"] == b and len(roh["paare"]) == 2,
           "die Wortlautdatei heisst nach der Sitzung und traegt sie auch drin")

    # Eine Antwort, die nach dem Schliessen fertig wird: Das Paar gehoert
    # dazu, und die Zusammenfassung muss ueberholt werden.
    sitzung.schliessen(b, JETZT + 32 * MIN)
    sitzung.marke_setzen(b, "zusammenfassung", "Es ging um zwei und drei.")
    sitzung.paar_anhaengen(b, "vier", "Antwort vier", JETZT + 32 * MIN)
    k = sitzung.kopf(b)
    pruefe(k["paare"] == 3 and k["zusammenfassung"] is None,
           "das Paar kommt dazu, die Zusammenfassung wird ueberholt")


def probe_anschluss_an_gespraech() -> None:
    """Die Naht zu gespraech.py. Ohne diese Probe ist A gebaut und nicht
    angeschlossen - und das faellt erst auf, wenn Calvin fragt."""
    print("\nAngeschlossen: was gespraech.py mit der Frage-JSON macht")
    frisch()
    import gespraech
    zuordnen = gespraech.Gespraech._sitzung_zuordnen
    ts = gespraech.Gespraech._frage_ts

    pruefe(abs(ts({"ts": JETZT}) - JETZT) < 1, "Sekunden werden genommen")
    pruefe(abs(ts({"ts": JETZT * 1000}) - JETZT) < 1,
           "Millisekunden werden erkannt, nicht 56000 Jahre daraus")
    for unsinn in ({}, {"ts": None}, {"ts": "morgen"}, {"ts": 0},
                   {"ts": 9e12}):
        pruefe(abs(ts(unsinn) - time.time()) < 5,
               "Unsinn wird zu jetzt: %r" % unsinn)

    # Eine echte Frage-JSON, wie die App sie schreibt.
    daten = {"id": "g-1", "ts": JETZT, "text": "Wie ist die Lage?",
             "status": "offen", "von": NUTZER}
    daten["sitzung"] = zuordnen(daten)
    pruefe(daten["sitzung"], "die Frage bekommt eine Sitzung: %s"
           % daten["sitzung"])

    zweite = {"id": "g-2", "ts": JETZT + 60, "text": "Und der Speicher?",
              "status": "offen", "von": NUTZER}
    zweite["sitzung"] = zuordnen(zweite)
    pruefe(zweite["sitzung"] == daten["sitzung"],
           "die Nachfrage eine Minute spaeter dieselbe")

    test = {"id": "g-test-3", "ts": JETZT + 70, "text": "Testfrage",
            "von": "test"}
    test["sitzung"] = zuordnen(test)
    pruefe(test["sitzung"] is None, "eine Testfrage bekommt None")
    pruefe(len(sitzung.lesen()) == 1, "und es bleibt bei einer Sitzung")


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print("Festes Jetzt: %s" % JETZT_D.strftime("%A, %d.%m.%Y, %H:%M"))
    echte = sitzung.KOEPFE
    for probe in (probe_zuordnung, probe_ruhe, probe_anschluss,
                  probe_obergrenze, probe_test_bekommt_keine,
                  probe_zwei_absender, probe_reinrutschen,
                  probe_wieder_aufnehmen, probe_faellig_und_neustart,
                  probe_ansprache, probe_finden, probe_platte,
                  probe_anschluss_an_gespraech):
        probe()
        wegraeumen()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    print("die echte Ablage (%s) wurde nicht angefasst" % echte.name)
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
