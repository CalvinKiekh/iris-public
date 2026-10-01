"""Probe fuer anlaesse.py - und, mit --echt, fuer den Satz, den er daraus macht.

    python anlaesse_test.py          nur messen, kein Modell, nichts veraendert
    python anlaesse_test.py --echt   dazu: gpt-oss formuliert die echten
                                     Anlaesse von jetzt

Die Probe fasst die Werkstatt NICHT an. Alle Pfade des Moduls zeigen waehrend
des Laufs in ein Wegwerf-Verzeichnis; am Ende stehen sie wieder, wo sie waren.
Sonst haette eine Messung die Anlaesse abgehakt, ueber die er dann nie spricht.
"""
from __future__ import annotations

from einstellungen import NAME
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import probenort
import pruefstand
import anlaesse

GESAMT = 0
FEHLER = 0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


class Werkstatt:
    """Ein Wegwerf-Verzeichnis, auf das das Modul waehrend des Tests zeigt."""

    FELDER = ("WERKSTATT", "JOURNAL", "ANTRAEGE", "LAGE", "PLATZVERLAUF",
              "WUENSCHE", "FAEHIGKEITEN", "WERKZEUGE", "ZUSTAND")

    def __enter__(self):
        self.vorher = {f: getattr(anlaesse, f) for f in self.FELDER}
        self.ort = probenort.ablage("anlaesse")
        anlaesse.WERKSTATT = self.ort
        anlaesse.JOURNAL = self.ort / "journal.jsonl"
        anlaesse.ANTRAEGE = self.ort / "antraege"
        anlaesse.LAGE = self.ort / "lage.json"
        anlaesse.PLATZVERLAUF = self.ort / "platzverlauf.jsonl"
        anlaesse.WUENSCHE = self.ort / "WUENSCHE.md"
        anlaesse.FAEHIGKEITEN = self.ort / "faehigkeiten.json"
        anlaesse.WERKZEUGE = self.ort / "werkzeuge.json"
        anlaesse.ZUSTAND = self.ort / "anlaesse.json"
        anlaesse.ANTRAEGE.mkdir()
        return self

    def __exit__(self, *_):
        for f, wert in self.vorher.items():
            setattr(anlaesse, f, wert)
        probenort.wegraeumen(self.ort)

    def journal(self, zeilen: list[dict]) -> None:
        anlaesse.JOURNAL.write_text(
            "\n".join(json.dumps(z, ensure_ascii=False) for z in zeilen),
            encoding="utf-8")

    def datei(self, name: str, inhalt: str = "x") -> str:
        p = self.ort / name
        p.write_text(inhalt, encoding="utf-8")
        return str(p)


def vor(minuten: float) -> float:
    return time.time() - minuten * 60


# --------------------------------------------------------------------- Proben


def probe_fertig() -> None:
    print(f"\nfertig - was {NAME} angestossen hat")
    with Werkstatt() as w:
        w.journal([
            {"ts": vor(30), "kind": "zuruf", "text": "Zieh den Antrag zurück"},
            {"ts": vor(28), "kind": "ergebnis", "text": "Antrag zurückgezogen"},
            {"ts": vor(27), "kind": "pruefung", "text": "Status geprüft"},
        ])
        a = anlaesse.fertig_geworden(anlaesse.journalzeilen(120))
        pruefe(len(a) == 1,
               "ein Zuruf mit Ergebnis UND Pruefung ist ein Vorgang, nicht "
               "zwei (%d)" % len(a))
        pruefe(a and "Zieh den Antrag" in a[0]["text"]
               and "Status geprüft" in a[0]["text"],
               f"der Anlass traegt beides: was {NAME} sagte und was herauskam")

    with Werkstatt() as w:
        w.journal([{"ts": vor(10), "kind": "ergebnis", "text": "irgendwas"}])
        pruefe(not anlaesse.fertig_geworden(anlaesse.journalzeilen(120)),
               f"ein Ergebnis ohne Zuruf davor ist nichts, was {NAME} anging")

    with Werkstatt() as w:
        w.journal([
            {"ts": vor(120), "kind": "zuruf", "text": "mach mal"},
            {"ts": vor(10), "kind": "ergebnis", "text": "fertig"},
        ])
        pruefe(not anlaesse.fertig_geworden(anlaesse.journalzeilen(240)),
               "zwei Stunden spaeter ist es Zufall, kein Zusammenhang")


def probe_dateien() -> None:
    print("\nneu_gesehen - Dateien")
    with Werkstatt() as w:
        pfad = w.datei("notiz.txt")
        w.journal([{"ts": vor(20), "kind": "fund", "wahrnehmung": True,
                    "datei": pfad, "text": "Eine Notiz über Zahlen."}])
        a = anlaesse.neu_gesehene_dateien(anlaesse.journalzeilen(120))
        pruefe(len(a) == 1 and "notiz.txt" in a[0]["text"],
               "eine verstandene Datei ist ein Anlass")

    with Werkstatt() as w:
        w.journal([{"ts": vor(20), "kind": "fund", "wahrnehmung": True,
                    "datei": str(w.ort / "weg.txt"), "text": "Eine Liste."}])
        pruefe(not anlaesse.neu_gesehene_dateien(anlaesse.journalzeilen(120)),
               "eine Datei, die es nicht mehr gibt, erzaehlt er nicht - "
               f"{NAME} koennte nicht nachsehen")

    with Werkstatt() as w:
        pfad = w.datei("da.txt")
        w.journal([{"ts": vor(20), "kind": "fund", "datei": pfad,
                    "text": "irgendein Fund"}])
        pruefe(not anlaesse.neu_gesehene_dateien(anlaesse.journalzeilen(120)),
               "ein gewoehnlicher Fund ist keine Wahrnehmung")


def probe_geraete() -> None:
    print("\nneu_gesehen - Geraete")
    with Werkstatt() as w:
        anlaesse.LAGE.write_text(json.dumps({"netz": [
            {"mac": "aa-01", "ip": "192.168.0.2", "gesehen": 9, "name": "Mac"},
            {"mac": "aa-02", "ip": "192.168.0.3", "gesehen": 9},
        ]}), encoding="utf-8")
        d = anlaesse.zustand_lesen()
        pruefe(not anlaesse.neue_geraete(d),
               "beim allerersten Lauf wird stumm abgehakt - vierzehn Geraete "
               "auf einmal waeren Laerm")

        anlaesse.LAGE.write_text(json.dumps({"netz": [
            {"mac": "aa-01", "ip": "192.168.0.2", "gesehen": 9, "name": "Mac"},
            {"mac": "aa-02", "ip": "192.168.0.3", "gesehen": 9},
            {"mac": "aa-03", "ip": "192.168.0.9", "gesehen": 4,
             "hostname": "drucker"},
            {"mac": "aa-04", "ip": "192.168.0.8", "gesehen": 1},
        ]}), encoding="utf-8")
        a = anlaesse.neue_geraete(d)
        pruefe(len(a) == 1 and "drucker" in a[0]["text"],
               "das neue Geraet ist ein Anlass, mit Namen")
        pruefe(all("aa-04" not in x["schluessel"] for x in a),
               "einmal aufgeblitzt ist nicht da - die ARP-Tabelle flackert")
        pruefe(not anlaesse.neue_geraete(d),
               "beim zweiten Blick ist es nicht mehr neu")


def probe_gelernt() -> None:
    print("\ngelernt - Faehigkeiten und Wuensche")
    with Werkstatt() as w:
        anlaesse.FAEHIGKEITEN.write_text(json.dumps(
            [{"name": "rueckblick", "zweck": "Die Nacht zusammenfassen"}]),
            encoding="utf-8")
        anlaesse.WERKZEUGE.write_text("[]", encoding="utf-8")
        d = anlaesse.zustand_lesen()
        pruefe(not anlaesse.neue_faehigkeiten(d), "erster Lauf: stumm")

        anlaesse.WERKZEUGE.write_text(json.dumps(
            [{"name": "netz", "zweck": "Wer im Heimnetz ist"}]),
            encoding="utf-8")
        a = anlaesse.neue_faehigkeiten(d)
        pruefe(len(a) == 1 and "netz" in a[0]["text"]
               and "Heimnetz" in a[0]["text"],
               "eine neue Faehigkeit ist ein Anlass, mit ihrem Zweck")

    with Werkstatt() as w:
        anlaesse.WUENSCHE.write_text(
            "# Wünsche\n\n"
            "Wie ich eine Firewall aktiviere.\n"
            "  Es fehlt: Wissen - kann ich mir selbst bauen lassen.\n\n"
            "Eine zweite Festplatte für die Protokolle.\n"
            f"  Es fehlt: Gerät - das kann nur {NAME}.\n",
            encoding="utf-8")
        d = anlaesse.zustand_lesen()
        pruefe(not anlaesse.wuensche_an_den_nutzer(d), "erster Lauf: stumm")

        anlaesse.WUENSCHE.write_text(
            anlaesse.WUENSCHE.read_text(encoding="utf-8")
            + "\nEin Recht, den Router neu zu starten.\n"
              f"  Es fehlt: Recht - das kann nur {NAME}.\n",
            encoding="utf-8")
        a = anlaesse.wuensche_an_den_nutzer(d)
        pruefe(len(a) == 1 and "Router" in a[0]["text"],
               "ein neuer Wunsch nach einem RECHT ist ein Anlass")
        pruefe(all("Firewall" not in x["text"] for x in a),
               "ein Wunsch nach WISSEN nicht - den kann er sich selbst "
               f"bauen lassen, dafuer braucht es {NAME} nicht")


def probe_antraege() -> None:
    print(f"\nfrage - was nur {NAME} entscheiden kann")
    with Werkstatt() as w:
        (anlaesse.ANTRAEGE / "a-1.json").write_text(json.dumps(
            {"id": "a-1", "ts": vor(10), "title": "Frisch", "reason": "x"}),
            encoding="utf-8")
        (anlaesse.ANTRAEGE / "a-2.json").write_text(json.dumps(
            {"id": "a-2", "ts": vor(400), "title": "Liegt seit Stunden",
             "reason": "x"}), encoding="utf-8")
        (anlaesse.ANTRAEGE / "a-3.json").write_text(json.dumps(
            {"id": "a-3", "ts": vor(400), "title": "Entschieden",
             "reason": "x", "decided": time.time()}), encoding="utf-8")
        (anlaesse.ANTRAEGE / "a-4.json").write_text(json.dumps(
            {"id": "a-4", "ts": vor(400), "title": "Zurückgezogen",
             "reason": "x", "status": "zurueckgezogen"}), encoding="utf-8")
        a = anlaesse.offene_antraege()
        pruefe(len(a) == 1 and a[0]["schluessel"] == "antrag:a-2",
               "nur der, der wirklich haengt (%s)"
               % ", ".join(x["schluessel"] for x in a))
        pruefe(a and "6.7 Stunden" in a[0]["text"],
               "mit der Wartezeit - das ist die Nachricht, nicht der Antrag")


def probe_muster() -> None:
    print("\nmuster - was ueber die Zeit sichtbar wird")
    with Werkstatt() as w:
        zeilen = []
        for i in range(19):
            zeilen.append({"ts": vor(1000) + i, "kind": "fehler",
                           "text": "Gespräch: Traceback (most recent call "
                                   "last):\n  File \"C:\\...\", line 4"})
        w.journal(zeilen)
        pruefe(not anlaesse.fehler_muster(anlaesse.journalzeilen(24 * 60)),
               "neunzehn Fehler in einer Minute sind EIN Vorfall")

    with Werkstatt() as w:
        w.journal([{"ts": vor(60 * h), "kind": "fehler",
                    "text": "Wahrnehmung: ConnectError"} for h in (1, 3, 6, 9)])
        a = anlaesse.fehler_muster(anlaesse.journalzeilen(24 * 60))
        pruefe(len(a) == 1 and "4 Mal" in a[0]["text"],
               "viermal ueber acht Stunden ist ein Muster")
        pruefe(a and "\n" not in a[0]["text"],
               "ohne Zeilenumbrueche - es wird eine Push-Nachricht")

    with Werkstatt() as w:
        jetzt = datetime.now()
        anlaesse.PLATZVERLAUF.write_text("\n".join(
            json.dumps({"zeit": datetime.fromtimestamp(
                jetzt.timestamp() - (9 - i) * 3600).isoformat(),
                "frei_gb": 1580.0 - i * 6}) for i in range(9)),
            encoding="utf-8")
        a = anlaesse.platz_muster()
        pruefe(len(a) == 1 and "weniger" in a[0]["text"],
               "48 GB ueber neun Stunden sind ein Verlauf")

    with Werkstatt() as w:
        jetzt = datetime.now()
        anlaesse.PLATZVERLAUF.write_text("\n".join(
            json.dumps({"zeit": datetime.fromtimestamp(
                jetzt.timestamp() - (9 - i) * 3600).isoformat(),
                "frei_gb": 1580.0 - i * 0.2}) for i in range(9)),
            encoding="utf-8")
        pruefe(not anlaesse.platz_muster(),
               "zwei GB ueber neun Stunden sind Rauschen")


def probe_haus() -> None:
    print("\nhaus - was im Rechner passiert ist")
    import haus
    echt = (haus.ereignisse, haus.programme)
    jetzt = time.time()
    try:
        haus.ereignisse = lambda stunden=24: [
            {"ts": jetzt - 3600, "art": "absturz",
             "was": "llama-server.exe abgestuerzt",
             "gegenstand": "llama-server.exe", "windows": "Fehlerhafter …"},
            {"ts": jetzt - 1800, "art": "absturz",
             "was": "llama-server.exe abgestuerzt",
             "gegenstand": "llama-server.exe", "windows": "Fehlerhafter …"},
            {"ts": jetzt - 900, "art": "neustart",
             "was": "Der Rechner ist hochgefahren", "gegenstand": "",
             "windows": ""},
            # Zu alt fuer das Fenster - darf nicht auftauchen.
            {"ts": jetzt - 90000, "art": "absturz", "was": "altes.exe "
             "abgestuerzt", "gegenstand": "altes.exe", "windows": ""},
            # Keine der beiden Arten.
            {"ts": jetzt - 60, "art": "installiert", "was": "X installiert",
             "gegenstand": "X", "windows": ""},
        ]
        haus.programme = lambda: [{"name": "Steam", "fassung": "2.10"}]
        # Ein eigener Zustand, nicht der echte. zustand_lesen() hat hier
        # gestanden und las werkstatt/anlaesse.json - sobald der laufende
        # Bewohner die Datei anlegte, kannte die Probe "Steam" schon nicht,
        # dafuer aber 121 andere Programme, und schlug fehl. Eine Probe, die
        # vom Betrieb abhaengt, misst den Betrieb, nicht den Code.
        d = {"bekannt": {}, "gesagt": {}}
        a = anlaesse.im_haus(d, stunden=24)
        arten = [x["art"] for x in a]
        pruefe(all(x == "haus" for x in arten) and len(a) == 2,
               "zwei Faelle: der Absturz und der Neustart (%d)" % len(a))
        absturz = next((x for x in a if "llama" in x["text"]), None)
        pruefe(absturz and "2 Mal" in absturz["text"],
               "zweimal derselbe Absturz am selben Tag ist EIN Satz, nicht "
               "zwei Anrufe: %s" % (absturz["text"] if absturz else "-"))
        pruefe(all("altes.exe" not in x["text"] for x in a),
               "was aus dem Fenster gefallen ist, bleibt draussen")
        pruefe(all("installiert" not in x["text"] for x in a),
               "beim ersten Blick werden die vorhandenen Programme stumm "
               "abgehakt")

        haus.programme = lambda: [{"name": "Steam", "fassung": "2.10"},
                                  {"name": "Blender", "fassung": "4.2"}]
        a = anlaesse.im_haus(d, stunden=24)
        neu = [x for x in a if "Blender" in x["text"]]
        pruefe(len(neu) == 1 and "4.2" in neu[0]["text"],
               "ein neu installiertes Programm ist ein Anlass: %s"
               % (neu[0]["text"] if neu else "-"))
    finally:
        haus.ereignisse, haus.programme = echt


def probe_reihenfolge_und_gedaechtnis() -> None:
    print("\nAuswahl - Rangfolge und was schon gesagt ist")
    with Werkstatt() as w:
        pfad = w.datei("neu.txt")
        w.journal([
            {"ts": vor(20), "kind": "fund", "wahrnehmung": True,
             "datei": pfad, "text": "Eine Notiz."},
            {"ts": vor(30), "kind": "zuruf", "text": "mach das"},
            {"ts": vor(29), "kind": "ergebnis", "text": "ist gemacht"},
        ])
        (anlaesse.ANTRAEGE / "a-9.json").write_text(json.dumps(
            {"id": "a-9", "ts": vor(400), "title": "Haengt", "reason": "x"}),
            encoding="utf-8")
        d = anlaesse.zustand_lesen()
        a = anlaesse.offen(d)
        pruefe([x["art"] for x in a[:3]] == ["frage", "fertig", "neu_gesehen"],
               "die Frage zuerst, dann das Fertige, dann das Gesehene (%s)"
               % ", ".join(x["art"] for x in a))

        anlaesse.vermerken(a[0], d)
        b = anlaesse.offen(d)
        pruefe(all(x["schluessel"] != a[0]["schluessel"] for x in b),
               "was vermerkt ist, kommt nicht wieder")
        pruefe(anlaesse.ZUSTAND.exists()
               and a[0]["schluessel"] in json.loads(
                   anlaesse.ZUSTAND.read_text(encoding="utf-8"))["gesagt"],
               "und es steht in der Datei - ein Neustart erzaehlt es nicht neu")


def probe_ohne_werkstatt() -> None:
    print("\nleere Werkstatt")
    with Werkstatt() as w:
        pruefe(anlaesse.offen(anlaesse.zustand_lesen()) == [],
               "kein Journal, keine Lage, kein Antrag - kein Anlass, "
               "und keine Ausnahme")


# ------------------------------------------------------- der echte Satz


def echte_anlaesse() -> None:
    """Was er JETZT sagen wuerde. Braucht Ollama und veraendert nichts."""
    import bewohner

    print("\n" + "=" * 70)
    print("Die echten Anlaesse von jetzt - und was gpt-oss daraus macht")
    print("=" * 70)
    versuche = 3
    for teil in sys.argv:
        if teil.startswith("--mal="):
            versuche = int(teil.split("=", 1)[1])

    alle = anlaesse.offen(anlaesse.zustand_lesen(), speichern=False)
    if not alle:
        print("\nKein Anlass. Er schwiege zu Recht.")
        return
    for a in alle:
        print(f"\n[{a['art']}] {a['schluessel']}")
        print(f"  gemessen: {a['text'][:200]}")
        gesagt = 0
        for i in range(versuche):
            t0 = time.time()
            satz, grund = bewohner.satz_zu_anlass(a)
            dauer = round(time.time() - t0, 1)
            if satz:
                gesagt += 1
                print(f"  {i + 1}. SAGT ({dauer}s, {len(satz)} Zeichen): {satz}")
                print(f"     weil: {grund}")
            else:
                print(f"  {i + 1}. schweigt ({dauer}s), weil: {grund}")
        print(f"  -> {gesagt} von {versuche} gesprochen")


def ganze_kette() -> None:
    """anlass_ansprechen() von Anfang bis Ende - aber ins Leere.

    Journal, Ansprachenverlauf und Anlasszustand zeigen waehrend des Laufs in
    ein Wegwerf-Verzeichnis. Es geht also KEINE Push an Calvin: Die Bruecke
    liest werkstatt/journal.jsonl, und dort steht danach nichts.

    Das ist Absicht. Der Beleg, den Calvin sehen will, ist eine Zeile aus dem
    laufenden Bewohner, nicht aus einer Probe - eine von hier aus erzeugte
    Push waere genau der Selbsttest, den er ausgeschlossen hat. Was diese
    Probe zeigt, ist der Weg: dass die Kette haelt, wenn der Bewohner sie geht.
    """
    print("\n" + "=" * 70)
    print("Die ganze Kette - in eine Wegwerf-Werkstatt, ohne Push")
    print("=" * 70)
    if not (pruefstand.bewohner_da() and pruefstand.werkzeug_da("ansprechen")):
        # The probe log has to lie inside his workshop - vermerken() refuses
        # anything else - so without him there is nowhere to put it.
        print("  --  hier wohnt kein Bewohner")
        return

    import bewohner
    sys.path.insert(0, str(Path(__file__).parent / "werkstatt" / "werkzeuge"))
    import ansprechen

    echte = {"JOURNAL": bewohner.JOURNAL, "ARTEN": bewohner.GEDAECHTNIS_ARTEN,
             "VERLAUF": ansprechen.VERLAUF, "darf": ansprechen.darf,
             "vermerken": ansprechen.vermerken}
    echter_verlauf = Path(echte["VERLAUF"])
    vorgefunden = (echter_verlauf.read_bytes()
                   if echter_verlauf.exists() else None)
    ort = probenort.ablage("kette")
    # Der Probeverlauf muss IN der Werkstatt liegen - vermerken() weigert
    # sich sonst, und zu Recht: ein Verlauf ausserhalb waere keiner. Der
    # Ordner steht in Beobachter.NICHT_BEOBACHTEN, damit die Probe ihn nicht
    # zum Nachdenken bringt, und er wird danach wieder entfernt.
    probe_ordner = Path(__file__).parent / "werkstatt" / "_anlaesse_probe"
    probe_ordner.mkdir(exist_ok=True)
    probe_verlauf = str(probe_ordner / "verlauf.jsonl")
    vorher = {f: getattr(anlaesse, f) for f in Werkstatt.FELDER}
    try:
        bewohner.JOURNAL = ort / "journal.jsonl"
        # Sonst schreibt die Probe echte Erinnerungen in gedaechtnis.db.
        bewohner.GEDAECHTNIS_ARTEN = set()
        anlaesse.ZUSTAND = ort / "anlaesse.json"
        # ansprechen.VERLAUF umzuhaengen GENUEGT NICHT: darf() und vermerken()
        # tragen den Pfad als Vorgabewert, und der ist beim Import gebunden.
        # Beim ersten Lauf dieser Probe stand danach eine erfundene Zeile in
        # der echten werkstatt/ansprachen.jsonl - und weil letzte() daraus den
        # Abstand rechnet, haette sie eine WIRKLICHE Ansprache eine Stunde
        # lang verhindert. Eine Probe, die das Gemessene veraendert.
        ansprechen.VERLAUF = probe_verlauf
        ansprechen.darf = (lambda text, dringend=False, jetzt=None,
                           verlauf=None: echte["darf"](text, dringend, jetzt,
                                                       probe_verlauf))
        ansprechen.vermerken = (lambda text, dringend=False, jetzt=None,
                                verlauf=None: echte["vermerken"](
                                    text, dringend, jetzt, probe_verlauf))

        print(f"\nist_ruhezeit   {ansprechen.ist_ruhezeit()}")
        print(f"ist_arbeitszeit {ansprechen.ist_arbeitszeit()}")
        ja, grund = ansprechen.darf("Probe")
        print(f"darf(beilaeufig) {ja} - {grund}")

        satz = bewohner.anlass_ansprechen()
        print(f"\nanlass_ansprechen() -> {satz!r}")

        print("\nWas ins Journal ginge:")
        if bewohner.JOURNAL.exists():
            for z in bewohner.JOURNAL.read_text(encoding="utf-8").splitlines():
                e = json.loads(z)
                print(f"  [{e['kind']}] {e['text'][:200]}")
                if e.get("anlass"):
                    print(f"      Anlass: {str(e['anlass'])[:120]}")
        else:
            print("  (nichts)")
        print("\nWas im Ansprachenverlauf staende:")
        p = Path(probe_verlauf)
        print("  " + (p.read_text(encoding="utf-8").strip()
                      if p.exists() else "(nichts)"))

        pruefe(not bewohner.JOURNAL.samefile(echte["JOURNAL"])
               if bewohner.JOURNAL.exists() else True,
               f"das echte Journal blieb unberuehrt - keine Push an {NAME}")
    finally:
        bewohner.JOURNAL = echte["JOURNAL"]
        bewohner.GEDAECHTNIS_ARTEN = echte["ARTEN"]
        ansprechen.VERLAUF = echte["VERLAUF"]
        ansprechen.darf = echte["darf"]
        ansprechen.vermerken = echte["vermerken"]
        for f, wert in vorher.items():
            setattr(anlaesse, f, wert)
        probenort.wegraeumen(ort)
        probenort.wegraeumen(probe_ordner)
        jetzt_da = (echter_verlauf.read_bytes()
                    if echter_verlauf.exists() else None)
        pruefe(jetzt_da == vorgefunden,
               "und der echte Ansprachenverlauf auch - sonst haette die "
               "Probe seinen Abstand verstellt")


def unberuehrt(pfad: Path):
    """Der Inhalt der Datei, oder None - zum Vergleich vorher und nachher."""
    return pfad.read_bytes() if pfad.exists() else None


def probe_ansprache_wache() -> None:
    """Was auf Calvins Sperrbildschirm nie erscheinen darf.

    Die allererste Ansprache, 12.09. um 11:47, lautete woertlich:

        "Ich habe die Datei a-1789201052.json auf Gerät X um 10:21 als
         zurückgezogen markiert."

    "Gerät X" stand in keinem Anlass - erfunden. Und "a-1789201052.json" ist
    eine Kennung aus seiner Werkstatt; Calvin kennt sie nicht. Der
    Systemtext verbietet inzwischen beides, aber eine Regel allein genuegt
    hier nicht: Dies ist die einzige Zeile, die ungefragt auf seinem Telefon
    klingelt, und sie laesst sich nicht zurueckholen.
    """
    import bewohner
    print("\ndie Wache vor dem Sperrbildschirm")
    schlecht = [
        ("Ich habe die Datei a-1789201052.json auf Gerät X um 10:21 als "
         "zurückgezogen markiert.", "der Satz von 11:47"),
        ("MoUsoCoreWorker laeuft, seit ?.", "seit ?"),
        ("Notiert für 2026-09-12T12:30:49.", "Maschinenzeitstempel"),
        ("Im Gespräch gab es einen JSONDecodeError.", "Fehlername"),
        ("Ich habe a-1789201052 geprüft.", "nackte Kennung"),
    ]
    for satz, was in schlecht:
        pruefe(bewohner.ansprache_mangel(satz) is not None,
               "zurueckgehalten (%s): %s" % (was, satz[:52]))

    gut = [
        "Der Antrag zum Löschen von wichtig.txt hat sich erledigt, ich habe "
        "ihn zurückgezogen.",
        "Ich habe um 10:16 eine Textdatei mit einer Einkaufsliste gefunden.",
        "Auf C sind noch 41 GB frei, gestern waren es 61.",
    ]
    for satz in gut:
        pruefe(bewohner.ansprache_mangel(satz) is None,
               "darf hinaus: %s" % satz[:52])


def main() -> int:
    print("Probe anlaesse")
    # Zweimal hat diese Probe in die ECHTE Werkstatt geschrieben, ohne dass es
    # jemandem auffiel: einmal in ansprachen.jsonl, einmal in anlaesse.json.
    # Beide Male haette das im Betrieb etwas verhindert - der Abstand und die
    # Anlaesse rechnen aus genau diesen Dateien. Eine Probe, die das Gemessene
    # veraendert, ist keine.
    echt = Path(__file__).parent / "werkstatt"
    wachen = {p: unberuehrt(p) for p in (echt / "anlaesse.json",
                                         echt / "ansprachen.jsonl")}

    probe_fertig()
    probe_dateien()
    probe_geraete()
    probe_gelernt()
    probe_antraege()
    probe_muster()
    probe_haus()
    probe_reihenfolge_und_gedaechtnis()
    probe_ohne_werkstatt()
    probe_ansprache_wache()
    print("\n%d von %d bestanden" % (GESAMT - FEHLER, GESAMT))

    if "--echt" in sys.argv:
        echte_anlaesse()
    if "--kette" in sys.argv:
        ganze_kette()

    print("\ndie echte Werkstatt")
    for p, vorher in wachen.items():
        pruefe(unberuehrt(p) == vorher,
               "%s ist unveraendert - die Probe hat nicht ins Echte "
               "geschrieben" % p.name)
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
