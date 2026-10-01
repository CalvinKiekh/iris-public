"""Probe fuer passiert.py.

    python passiert_test.py          Zeitraum und Auswahl, ohne Modell
    python passiert_test.py --echt   dazu: die echte Frage durch gespraech.py

Zwei Dinge werden geprueft, und beide sind Behauptungen ueber Wahrheit:
dass der Zeitraum stimmt, den er aus der Frage liest, und dass die Auswahl
nachvollziehbar ist. Wer auswaehlt, muss sagen koennen, warum.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import probenort
import passiert

GESAMT = 0
FEHLER = 0
# Ein Samstagvormittag, damit die Proben nicht davon abhaengen, wann sie
# laufen.
JETZT = datetime(2026, 9, 12, 11, 55)


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def spanne(frage: str, jetzt: datetime = JETZT):
    von, bis, name = passiert.zeitraum(frage, jetzt)
    return (datetime.fromtimestamp(von), datetime.fromtimestamp(bis), name)


def probe_zeitraum() -> None:
    print("\nden Zeitraum aus der Frage lesen (es ist Sa, 12.09., 11:55)")
    von, bis, name = spanne("Was ist letzte Nacht passiert?")
    pruefe(name == "letzte Nacht" and von.day == 11 and von.hour == 22
           and bis.day == 12 and bis.hour == 7,
           "letzte Nacht: %s bis %s" % (von.strftime("%d. %H:%M"),
                                        bis.strftime("%d. %H:%M")))

    for f in ("Wie war die Nacht?", "Erzähl mir von der Nacht",
              "Was war heute Nacht los?", "Ist nachts etwas passiert?"):
        pruefe(spanne(f)[2] == "letzte Nacht",
               "auch so gefragt: %s -> %s" % (f, spanne(f)[2]))

    von, bis, name = spanne("Was ist gestern passiert?")
    pruefe(name == "gestern" and von.day == 11 and von.hour == 0
           and bis.day == 12 and bis.hour == 0,
           "gestern ist ein ganzer Tag, nicht bis jetzt")

    von, bis, name = spanne("Was ist heute passiert?")
    pruefe(name == "heute" and von.day == 12 and von.hour == 0
           and abs((bis - JETZT).total_seconds()) < 2,
           "heute geht bis jetzt")

    von, _, name = spanne("Was ist in den letzten drei Stunden passiert?")
    pruefe(name == "in den letzten 3 Stunden" and von.hour == 8,
           "Zahlwort: %s" % name)
    von, _, name = spanne("Was ist in den letzten 20 Minuten passiert?")
    pruefe(name == "in den letzten 20 Minuten" and von.minute == 35,
           "Ziffer: %s" % name)

    von, _, name = spanne("Was ist vorgestern passiert?")
    pruefe(name == "vorgestern" and von.day == 10, "vorgestern")

    _, _, name = spanne("Was ist passiert?")
    pruefe(name == "in den letzten zwoelf Stunden",
           "ohne Zeitangabe zwoelf Stunden - und er sagt es auch so, "
           "damit es nicht klingt, als waere danach gefragt worden")

    # Mitten in der Nacht ist "letzte Nacht" die laufende.
    von, bis, _ = spanne("Was ist letzte Nacht passiert?",
                         datetime(2026, 9, 12, 3, 0))
    pruefe(von.day == 11 and von.hour == 22 and bis.hour == 3,
           "um 3 Uhr nachts endet die Nacht jetzt, nicht um 7")


def probe_erkennen() -> None:
    print("\nwelche Frage ueberhaupt eine nach dem Geschehen ist")
    for f in ("Was ist letzte Nacht passiert?", "Was ist heute passiert?",
              "Was war los?", "Gab es etwas Besonderes?",
              "Wie war die Nacht?", "Was hat sich verändert?",
              "Erzähl mir von gestern"):
        pruefe(passiert.ist_frage(f), "erkannt: %s" % f)
    for f in ("Wie spät ist es?", "Was kannst du alles?",
              "Wie viel Platz ist frei?", "Wer ist im Netz?",
              "Was hast du heute gemacht?"):
        pruefe(not passiert.ist_frage(f),
               "nicht erkannt, und das ist richtig: %s" % f)


def zeile(ts, art, text, quelle="journal", gegenstand=""):
    return {"ts": ts, "art": art, "text": text, "quelle": quelle,
            "gegenstand": gegenstand,
            "gewicht": (passiert.GEWICHT_EREIGNIS.get(art, 40)
                        if quelle == "windows"
                        else passiert.GEWICHT.get(art,
                                                  passiert.GEWICHT_UNBEKANNT))}


def probe_buendeln() -> None:
    print("\nWiederholungen zu einem Punkt")
    t = time.time()
    viele = [zeile(t + i, "haus", f"chrome laeuft, seit 09:{i:02d}.")
             for i in range(9)]
    a = passiert.buendeln(viele)
    pruefe(len(a) == 1 and a[0].get("anzahl") == 9,
           "neun gleiche Zeilen sind ein Punkt: %d" % len(a))

    # Der Fall, der beim ersten Lauf schiefging: In einer MAC stehen
    # Buchstaben, und die blosse Ziffernersetzung machte aus acht gleichen
    # Zeilen acht verschiedene.
    geraete = [zeile(t + i, "fund",
                     f"23:48 ist ein Gerät dazugekommen: 192.168.0.{40 + i} "
                     f"(80-23-95-23-a4-{40 + i})") for i in range(8)]
    a = passiert.buendeln(geraete)
    pruefe(len(a) == 1 and a[0].get("anzahl") == 8,
           "acht Geräte mit acht Adressen sind ein Vorgang: %d" % len(a))

    msi = [zeile(t + i, "installiert", "AMD Chipset wurde installiert",
                 "windows", "AMD Chipset") for i in range(71)]
    a = passiert.buendeln(msi)
    pruefe(len(a) == 1 and "71 Mal" in a[0]["text"],
           "einundsiebzig Installationsmeldungen eines Pakets: %s"
           % (a[0]["text"] if a else ""))

    zwei = [zeile(t, "fund", "etwas"), zeile(t + 1, "fund", "etwas")]
    pruefe(len(passiert.buendeln(zwei)) == 2,
           "zwei sind noch keine Wiederholung - sie bleiben einzeln")

    gemischt = [zeile(t, "fund", "A"), zeile(t + 1, "absturz", "B", "windows",
                                             "b.exe")]
    pruefe(len(passiert.buendeln(gemischt)) == 2,
           "Verschiedenes bleibt verschieden")


def probe_gewichte() -> None:
    print("\nwas nie in den Bericht kommt")
    for art in ("tick", "stimme", "frage", "antwort", "faden", "zeiten",
                "gedaechtnis", "nachtrag"):
        pruefe(passiert.GEWICHT[art] == 0,
               "%s ist eigene Maschinerie, kein Geschehen" % art)
    pruefe(passiert.GEWICHT["entscheidung"] > passiert.GEWICHT["fund"]
           > passiert.GEWICHT["fehler"],
           f"{NAMENS} Entscheidung wiegt mehr als ein Fund, ein Fund mehr "
           "als ein Fehler")
    pruefe(passiert.GEWICHT_EREIGNIS["neustart"]
           > passiert.GEWICHT_EREIGNIS["installiert"],
           "der Rechner war aus - groesser wird es nicht")
    # Eine Art ohne Eintrag ist nicht "mittelwichtig", sie ist ein Loch: sie
    # faellt stumm auf GEWICHT_UNBEKANNT=25 und damit unter `fund` (55). Am
    # 13.09. traf das `sitzung`, `verlust`, `ableiten_trocken` und
    # `kernwissen_fehlt` - und "Was ist letzte Nacht passiert?" bestand
    # daraufhin aus zwoelf Dateiaenderungen und sieben Bedarfsdiensten.
    # Deshalb ist das hier keine Liste von Hand, sondern ein Abgleich gegen
    # nacht.ARTEN: Kommt dort eine Art dazu, faellt sie hier auf.
    # Eine Testfrage ist kein Ereignis. Sie wird ausgelassen UND gezaehlt -
    # verschwiegen waere derselbe Fehler andersherum: "es ist nichts passiert"
    # ist falsch, wenn die Nacht voller Messungen war.
    meins = {"ts": 1.0, "kind": "sitzung", "text": "Es ging um den Desktop"}
    probe = dict(meins, von="test")
    pruefe(passiert.ist_vom_nutzer(meins) and not passiert.ist_vom_nutzer(probe),
           f"eine Zeile mit von=test gehoert nicht in {NAMENS} Chronik")
    pruefe(passiert.ist_vom_nutzer({"von": None}),
           "ein fehlendes Feld ist kein leeres Ergebnis - sie gilt als seine")

    import nacht
    fehlend = [a for a in nacht.ARTEN if a not in passiert.GEWICHT]
    pruefe(not fehlend,
           "jede Art, die der Nachtbericht fuer wichtig haelt, hat hier ein "
           "eigenes Gewicht: fehlt %s" % (fehlend or "keine"))
    pruefe(passiert.GEWICHT.get("kernwissen_fehlt", 0)
           > passiert.GEWICHT["fund"]
           and passiert.GEWICHT.get("sitzung", 0) > passiert.GEWICHT["haus"],
           "ein fehlendes Kernwissen und die Zusammenfassung eines Gespraechs "
           "wiegen mehr als eine Dateiaenderung und ein Dienst")
    # Was ein Modell BEHAUPTET, kommt nicht ueber das Gemessene. Der Fall:
    # "Abonnement sank from 0.7 to 0.0" wog als `fund` 55 und rangierte ueber
    # der Gegenpruefung, den Zusammenfassungen und dem Verlust der Werkstatt.
    pruefe(passiert.GEWICHT_MODELL_HOECHSTENS < passiert.GEWICHT["haus"]
           < passiert.GEWICHT["fund"],
           "eine Modellbehauptung wiegt weniger als ein gemessener Wert und "
           "weniger als ein bemerkter Fund")
    pruefe(passiert.GEWICHT_MODELL_HOECHSTENS > 0,
           "aber mehr als nichts - sie wird nicht verschwiegen")
    pruefe(passiert.GEWICHT["sitzung"] > passiert.GEWICHT_MODELL_HOECHSTENS,
           "eine Sitzungszusammenfassung behaelt ihr Gewicht: sie ist vom "
           "Modell formuliert, behauptet aber nichts, was nicht dastand")
    pruefe(bool(passiert._GELOESCHT.match("(vergessen)")),
           "eine geloeschte Zeile wird erkannt")
    pruefe(bool(passiert._NUR_DIE_UHR.match("05:00 begann der Morgen")),
           "\"begann der Morgen\" ist keine Auskunft ueber die Nacht")
    pruefe(not passiert._NUR_DIE_UHR.match(
        "23:48 ist ein Gerät dazugekommen: 192.168.0.1"),
        "ein Geraet dagegen schon")


def probe_bericht() -> None:
    print("\nder Bericht sagt, dass er ausgewaehlt hat")
    t = time.time() - 3600
    eintraege = ([zeile(t + i, "tick", "nichts zu tun") for i in range(500)]
                 + [zeile(t + 600, "zuruf", "(vergessen)")] * 3
                 + [zeile(t + 700, "antrag", "Ollama neu starten duerfen")])
    echt = passiert.sammeln
    passiert.sammeln = lambda *a, **k: sorted(eintraege,
                                              key=lambda e: e["ts"])
    try:
        # sammeln() setzt die Marken sonst selbst; hier von Hand.
        for e in eintraege:
            if e["text"] == "(vergessen)":
                e["gewicht"], e["geloescht"] = 0, True
        b = passiert.bericht(t, time.time(), "die letzte Stunde")
        pruefe(len(b["punkte"]) == 1
               and "Ollama" in b["punkte"][0]["was"],
               "von 504 Zeilen bleibt die eine, die zaehlt")
        pruefe(b["eigene_durchgaenge"] == 500,
               "und er sagt, dass 500 Durchgaenge dahinterstehen (%s)"
               % b["eigene_durchgaenge"])
        pruefe(b["geloescht"] == 3,
               "und dass drei Zeilen geloescht waren (%s)" % b["geloescht"])
        pruefe(b["insgesamt"] == 504, "und wie viele es insgesamt waren")

        pruefe(b["an_mir_gearbeitet"] == 0,
               "und dass keine Messung dabei war")

        # Dieselbe Stunde, aber die Haelfte waren Messfragen.
        fremd = [dict(zeile(t + 800, "sitzung", "Es ging um den Desktop"),
                      von="test") for _ in range(4)]
        passiert.sammeln = lambda *a, **k: sorted(
            eintraege + fremd, key=lambda e: e["ts"])
        m = passiert.bericht(t, time.time(), "die letzte Stunde")
        pruefe(all("Desktop" not in p["was"] for p in m["punkte"]),
               f"eine Messsitzung steht nicht in {NAMENS} Chronik")
        pruefe(m["an_mir_gearbeitet"] == 4,
               "aber sie wird gezaehlt und genannt (%s)"
               % m["an_mir_gearbeitet"])
        pruefe(m["insgesamt"] == 504,
               "und sie zaehlt nicht als seine Zeile mit (%s)"
               % m["insgesamt"])
    finally:
        passiert.sammeln = echt

    # Und die echte Zeile vom 13.09., durch aus_journal() gelesen: Der
    # Abo-Stand war ein `fund` (55) und lag damit ueber allem, was wirklich
    # geschehen ist.
    import json as _json
    import tempfile as _tmp
    from pathlib import Path as _P

    echt_j = passiert.JOURNAL
    _o = _P(_tmp.mkdtemp(prefix="passiert_modell_"))
    try:
        t0 = time.time() - 600
        _o.joinpath("j.jsonl").write_text("".join(_json.dumps(e) + "\n" for e in (
            {"ts": t0, "kind": "fund", "text": "Abonnement sank from 0.7 to 0.0",
             "modell": True},
            {"ts": t0 + 1, "kind": "fund", "text": "Eine Datei wurde geaendert."},
            {"ts": t0 + 2, "kind": "haus", "text": "Die CPU liegt bei 59 Prozent."},
        )), encoding="utf-8")
        passiert.JOURNAL = _o / "j.jsonl"
        nach_art = {e["art"] + ("/modell" if e["modell"] else ""): e["gewicht"]
                    for e in passiert.aus_journal(t0 - 10, time.time())}
        pruefe(nach_art["fund/modell"] < nach_art["fund"],
               "die Modellbehauptung wiegt weniger als der gemessene Fund: "
               "%s" % nach_art)
        pruefe(nach_art["fund/modell"] < nach_art["haus"],
               "und weniger als der gemessene CPU-Wert - genau die Umkehrung "
               "von heute Nacht")
    finally:
        passiert.JOURNAL = echt_j
        import shutil as _sh

        _sh.rmtree(_o, ignore_errors=True)

    echt = passiert.sammeln
    try:

        passiert.sammeln = lambda *a, **k: []
        leer = passiert.bericht(t, time.time(), "die letzte Stunde")
        pruefe(leer["punkte"] == [] and leer["insgesamt"] == 0,
               "und wenn nichts war, ist der Bericht leer statt erfunden")
    finally:
        passiert.sammeln = echt


def probe_echt() -> None:
    print("\nder echte Bericht ueber die letzte Nacht")
    t0 = time.time()
    b = passiert.zur_frage("Was ist letzte Nacht passiert?")
    dauer = round(time.time() - t0, 1)
    print(f"  {b['zeitraum']}, {b['von']} bis {b['bis']}, in {dauer} s")
    for p in b["punkte"]:
        print(f"    {p['zeit']}  [{p['art']}] {p['was'][:96]}")
    print(f"  {b['insgesamt']} Zeilen, {b['eigene_durchgaenge']} eigene "
          f"Durchgaenge, {b['geloescht']} geloescht, "
          f"{b['nicht_genannt']} weitere nicht genannt")
    pruefe(len(b["punkte"]) <= passiert.PUNKTE_HOECHSTENS,
           "hoechstens %d Punkte" % passiert.PUNKTE_HOECHSTENS)
    pruefe(all(p["art"] not in ("tick", "stimme", "nachtrag")
               for p in b["punkte"]),
           "keine eigene Maschinerie im Bericht")
    pruefe(all(p["was"] != "(vergessen)" for p in b["punkte"]),
           "nichts Geloeschtes im Bericht")
    # Ueber Mitternacht hinweg laufen die Uhrzeiten als TEXT rueckwaerts:
    # "23:55" steht vor "02:11", ist aber groesser. Genau eine solche Stelle
    # darf es geben - zwei hiessen, dass die Reihenfolge wirklich falsch ist.
    zeiten = [p["zeit"] for p in b["punkte"]]
    rueckwaerts = sum(1 for a, z in zip(zeiten, zeiten[1:]) if z < a)
    pruefe(rueckwaerts <= 1,
           "in der Reihenfolge der Zeit, mit hoechstens einem Sprung ueber "
           "Mitternacht (%d) - eine Nacht ist eine Abfolge, keine Rangliste"
           % rueckwaerts)


def echte_antwort() -> None:
    from gespraech import Gespraech
    print("\n" + "=" * 70)
    print(f"Die Frage durch gespraech.py, wie {NAME} sie stellt")
    print("=" * 70)
    p = Path(__file__).parent / "werkstatt" / "_passiert_probe"
    p.mkdir(exist_ok=True)
    try:
        g = Gespraech(p, lambda *a, **k: None, Path("x.wav"))
        for frage in ("Was ist letzte Nacht passiert?",
                      "Was ist in den letzten zwei Stunden passiert?"):
            t0 = time.time()
            a = g._antwort_holen(frage, {"state": "wach"}, {"vorgaenge": []})
            print(f"\nFRAGE: {frage}")
            print(f"  ({round(time.time() - t0, 1)} s) {a}")
            pruefe(bool(a) and len(a) > 20, "er antwortet")
    finally:
        probenort.wegraeumen(p)


def probe_menschlich() -> None:
    """Was vorgelesen wird, traegt nichts aus dem Inneren.

    Die Faelle stammen wortgetreu aus dem Journal vom 12.09. - es sind die
    Zeilen, die Calvin vorgelesen bekommen hat.
    """
    print("\nvorgelesen wird nichts aus dem Inneren")
    faelle = [
        ("Fehler-Traceback bei Gespraech", "Traceback", "Fehler"),
        ('Gespräch: Traceback (most recent call last): File "bewohner.py"',
         "Traceback", "Fehler"),
        ("Antwort unlesbar (JSONDecodeError)", "JSONDecodeError", "Fehler"),
        ("Ollama weg: ConnectError", "ConnectError", "Fehler"),
        ("neues Gerät 192.168.0.1 angeschlossen", "192.168", "Gerät"),
        ("a-1789201052.json zurückgezogen", "1789201052", "Antrag"),
        ("Notiert für 2026-09-12T12:30:49", "2026-09-12T", "12:30"),
    ]
    for roh, darf_nicht, muss in faelle:
        raus = passiert.menschlich(roh)
        pruefe(darf_nicht not in raus and muss in raus,
               "%r -> %r" % (roh[:44], raus[:58]))

    # Eine Adresse OHNE das Wort Geraet muss benannt werden, nicht wegfallen -
    # sonst bliebe "ist neu im Netz" ohne Gegenstand stehen.
    raus = passiert.menschlich("192.168.0.1 ist neu im Netz")
    pruefe("Gerät im Heimnetz" in raus and "192.168" not in raus,
           "eine Adresse allein wird benannt: %r" % raus)

    # Und eine saubere Zeile bleibt unangetastet. Eine Saeuberung, die auch
    # das Gute umschreibt, richtet mehr an, als sie behebt.
    gut = "Eine Textdatei mit einer Einkaufsliste gefunden."
    pruefe(passiert.menschlich(gut) == gut,
           "was sauber ist, wird nicht angefasst: %r"
           % passiert.menschlich(gut))


def main() -> int:
    print("Probe passiert")
    probe_zeitraum()
    probe_erkennen()
    probe_buendeln()
    probe_gewichte()
    probe_bericht()
    probe_menschlich()
    probe_echt()
    if "--echt" in sys.argv:
        echte_antwort()
    print("\n%d von %d bestanden" % (GESAMT - FEHLER, GESAMT))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
