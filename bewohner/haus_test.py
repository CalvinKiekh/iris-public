"""Probe fuer haus.py.

    python haus_test.py          nur die Vergleichslogik, ohne zu messen
    python haus_test.py --echt   dazu: zweimal wirklich messen

Der Kern von haus.py ist nicht die Messung, sondern der VERGLEICH. "Was ist
passiert" ist eine Frage nach Veraenderung. Die Fallen sitzen alle dort:
ein Prozess, der nur aus der Bestenliste faellt, ist nicht gestorben; ein
Arbeitsspeicher, der um 40 MB schwankt, hat sich nicht veraendert.

Es wird nichts in die Werkstatt geschrieben.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import probenort
import haus

GESAMT = 0
FEHLER = 0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def zustand(**anders) -> dict:
    """Ein vollstaendiges Hausbild, das man stueckweise verstellen kann."""
    jetzt = time.time()
    d = {
        "ts": jetzt,
        "maschine": {"rechner": "PC", "cpu_kerne": 16, "cpu_last": 5,
                     "ram_gesamt_gb": 61.6, "ram_frei_gb": 40.0,
                     "hochgefahren": jetzt - 90000, "windows": "Windows 11"},
        "platten": [{"laufwerk": "C:", "frei_gb": 1500.0,
                     "gesamt_gb": 3814.4}],
        "prozesse": [{"name": "chrome", "pid": 1, "ram_mb": 500,
                      "cpu_s": 10.0, "seit": jetzt - 3600}],
        "namen": [{"name": "chrome", "anzahl": 4, "seit": jetzt - 3600},
                  {"name": "ollama", "anzahl": 1, "seit": jetzt - 7200},
                  {"name": "explorer", "anzahl": 1, "seit": jetzt - 80000}],
        "dienste": {"laufen": 157, "insgesamt": 320, "sollen_aber_aus": [],
                    "aus_roh": [], "wechsel": {}, "bedarf": []},
        "gpu": {"name": "RTX 5080", "last_prozent": 6, "speicher_mb": 13000,
                "speicher_gesamt_mb": 16303, "temperatur_c": 36},
    }
    for schluessel, wert in anders.items():
        if isinstance(wert, dict) and isinstance(d.get(schluessel), dict):
            d[schluessel] = {**d[schluessel], **wert}
        else:
            d[schluessel] = wert
    return d


def probe_erster_blick() -> None:
    print("\nder erste Blick stellt fest, er vergleicht nicht")
    pruefe(haus.veraenderungen({}, zustand()) == [],
           "ohne Vorher keine Veraenderung - sonst waere beim Start das "
           "ganze Haus 'neu'")
    pruefe(haus.veraenderungen(zustand(), zustand()) == [],
           "zweimal dasselbe ist keine Veraenderung")


def probe_rauschen() -> None:
    print("\nRauschen darf keine Veraenderung sein")
    alt = zustand()
    pruefe(haus.veraenderungen(
        alt, zustand(maschine={"ram_frei_gb": 40.4})) == [],
        "400 MB Arbeitsspeicher hin oder her sind nichts")
    pruefe(haus.veraenderungen(
        alt, zustand(platten=[{"laufwerk": "C:", "frei_gb": 1498.0,
                               "gesamt_gb": 3814.4}])) == [],
        "zwei GB auf einer Vier-Terabyte-Platte sind nichts")
    pruefe(haus.veraenderungen(alt, zustand(maschine={"cpu_last": 20})) == [],
           "die CPU springt staendig - erst eine Stufe zaehlt")
    pruefe(haus.veraenderungen(
        alt, zustand(gpu={"last_prozent": 94})) == [],
        "auch die GPU-Auslastung ist zu sprunghaft zum Vergleichen")


def probe_echte_veraenderung() -> None:
    print("\nund was eine ist")
    alt = zustand()
    a = haus.veraenderungen(alt, zustand(maschine={"ram_frei_gb": 12.0}))
    pruefe(len(a) == 1 and "12.0" in a[0] and "40.0" in a[0],
           "der Arbeitsspeicher faellt von 40 auf 12 GB: %s" % (a or "nichts"))

    a = haus.veraenderungen(alt, zustand(maschine={"cpu_last": 95}))
    pruefe(len(a) == 1 and "95" in a[0], "die CPU geht auf 95 Prozent")

    a = haus.veraenderungen(
        alt, zustand(platten=[{"laufwerk": "C:", "frei_gb": 1400.0,
                               "gesamt_gb": 3814.4}]))
    pruefe(len(a) == 1 and "100" in a[0] and "weniger" in a[0],
           "100 GB weniger auf C: %s" % (a or "nichts"))

    a = haus.veraenderungen(
        alt, zustand(maschine={"hochgefahren": time.time() - 300}))
    pruefe(any("neu gestartet" in z and "Rechner" in z for z in a),
           "der Rechner war aus - die groesste Veraenderung, die es gibt")

    a = haus.veraenderungen(
        alt, zustand(gpu={"speicher_mb": 2000}))
    pruefe(len(a) == 1 and "2000" in a[0],
           "elf Gigabyte auf der Grafikkarte freigeworden: %s" % (a or "nichts"))


def probe_prozesse() -> None:
    print("\nProzesse - hier sitzen die Fallen")
    jetzt = time.time()
    alt = zustand()

    neu = zustand(namen=[n for n in zustand()["namen"]
                         if n["name"] != "ollama"])
    a = haus.veraenderungen(alt, neu)
    pruefe(a == ["ollama laeuft nicht mehr."],
           "ein verschwundener Prozess wird gemeldet: %s" % a)

    # Die wichtigste Probe: aus der Bestenliste fallen ist nicht sterben.
    neu = zustand(prozesse=[{"name": "chrome2", "pid": 9, "ram_mb": 900,
                             "cpu_s": 1.0, "seit": jetzt - 60}])
    pruefe(haus.veraenderungen(alt, neu) == [],
           "wer nur aus den groessten zwoelf faellt, laeuft weiter - "
           "\"laeuft nicht mehr\" waere schlicht falsch")

    neu = zustand(namen=zustand()["namen"]
                  + [{"name": "SwarmUI", "anzahl": 1, "seit": jetzt - 300}])
    a = haus.veraenderungen(alt, neu)
    pruefe(len(a) == 1 and "SwarmUI" in a[0] and "laeuft, seit" in a[0],
           "ein neuer Prozess wird gemeldet: %s" % a)

    neu = zustand(namen=zustand()["namen"]
                  + [{"name": "tasklist", "anzahl": 1, "seit": jetzt - 2}])
    pruefe(haus.veraenderungen(alt, neu) == [],
           "ein Aufruf, der zwei Sekunden dauert, ist kein Ereignis im Haus")

    # Bei Systemprozessen ist die Startzeit nicht lesbar. Im Journal stand
    # deshalb am 12.09. um 11:52 "MoUsoCoreWorker laeuft, seit ?."
    ohne_zeit = {"name": "MoUsoCoreWorker", "anzahl": 1, "seit": None}
    neu = zustand(namen=zustand()["namen"] + [ohne_zeit])
    pruefe(haus.veraenderungen(alt, neu) == [],
           "ohne messbare Startzeit gar keine Meldung - wer nicht sagen "
           "kann, seit wann, hat nicht gemessen, dass es neu ist")
    pruefe(haus.veraenderungen(neu, zustand()) == [],
           "und so einer verschwindet auch nicht")

    neu = zustand(namen=[{**n, "seit": jetzt - 30} if n["name"] == "ollama"
                         else n for n in zustand()["namen"]])
    a = haus.veraenderungen(alt, neu)
    pruefe(len(a) == 1 and "ollama" in a[0] and "neu gestartet" in a[0],
           "der aelteste Start springt nach vorn: neu gestartet, %s" % a)

    neu = zustand(namen=[{**n, "anzahl": 9} if n["name"] == "chrome" else n
                         for n in zustand()["namen"]])
    pruefe(haus.veraenderungen(alt, neu) == [],
           "fuenf Browserfenster mehr sind kein Ereignis")


def probe_unsere_werkzeuge() -> None:
    print("\nwas wir beide beim Arbeiten erzeugen, ist keine Veraenderung")
    jetzt = time.time()
    alt = zustand()
    for name in ("python", "pythonw3.10", "claude", "sshd", "powershell",
                 "conhost", "bash"):
        neu = zustand(namen=zustand()["namen"]
                      + [{"name": name, "anzahl": 1, "seit": jetzt - 600}])
        pruefe(haus.veraenderungen(alt, neu) == [],
               "%s taucht auf - kein Ereignis" % name)
        pruefe(haus.veraenderungen(neu, alt) == [],
               "%s verschwindet - auch keins" % name)
    # Und der Gegenbeweis: Der Dienst, mit dem er denkt, zaehlt sehr wohl.
    # ollama steht schon im Grundzustand - hier faellt es weg.
    ohne_ollama = zustand(namen=[n for n in zustand()["namen"]
                                 if n["name"] != "ollama"])
    pruefe(haus.veraenderungen(zustand(), ohne_ollama)
           == ["ollama laeuft nicht mehr."],
           "ollama steht NICHT auf der Ausnahmeliste - wenn der Dienst "
           "verschwindet, mit dem er denkt, will er das wissen: %s"
           % haus.veraenderungen(zustand(), ohne_ollama))


def probe_bestaetigt() -> None:
    print("\nzwei Messungen, sonst hat es nie existiert")
    jetzt = time.time()
    lang = {"name": "SwarmUI", "anzahl": 1, "seit": jetzt - 600}
    leer = {"namen": [], "namen_roh": []}

    # Erster Blick: alles gilt sofort, sonst meldete jeder Neustart alles neu.
    eins = haus._bestaetigt(leer, {"namen": [lang]})
    pruefe([p["name"] for p in eins["namen"]] == ["SwarmUI"],
           "der erste Blick stellt fest, er vergleicht nicht")

    # Ein Kurzlaeufer, der lang genug lebt, um _ohne_junge zu ueberstehen:
    # einmal gesehen reicht nicht.
    kurz = {"name": "python", "anzahl": 1, "seit": jetzt - 25}
    vorher = {"namen": [lang], "namen_roh": [lang]}
    a = haus._bestaetigt(vorher, {"namen": [lang, kurz]})
    pruefe([p["name"] for p in a["namen"]] == ["SwarmUI"],
           "einmal gesehen ist noch nicht da: %s"
           % [p["name"] for p in a["namen"]])

    # Beim zweiten Mal schon.
    b = haus._bestaetigt(a, {"namen": [lang, kurz]})
    pruefe(sorted(p["name"] for p in b["namen"]) == ["SwarmUI", "python"],
           "zweimal hintereinander gesehen heisst da")

    # Und einmal gefehlt ist noch nicht weg.
    c = haus._bestaetigt(b, {"namen": [lang]})
    pruefe(sorted(p["name"] for p in c["namen"]) == ["SwarmUI", "python"],
           "einmal gefehlt ist noch nicht weg - und der Eintrag bleibt "
           "stehen, sonst meldet veraenderungen() ihn genau jetzt als "
           "verschwunden: %s" % [p["name"] for p in c["namen"]])
    pruefe(haus.veraenderungen(b, c) == [],
           "und genau deshalb faellt in der Gnadenmessung keine Zeile an")
    d = haus._bestaetigt(c, {"namen": [lang]})
    pruefe([p["name"] for p in d["namen"]] == ["SwarmUI"],
           "zweimal gefehlt heisst weg")

    # Der Fall, um den es geht: ein Prozess, den es nur in EINER Messung
    # gibt, erzeugt nie eine Veraenderung - weder beim Kommen noch beim Gehen.
    v1 = haus._bestaetigt(vorher, {"namen": [lang, kurz]})
    v2 = haus._bestaetigt(v1, {"namen": [lang]})
    pruefe(haus.veraenderungen(vorher, v1) == []
           and haus.veraenderungen(v1, v2) == [],
           "ein Aufblitzen erzeugt keine einzige Zeile - das waren die "
           "44 Journalzeilen ueber python.exe")


def probe_bedarf_namen() -> None:
    """Calvins Zaehlung vom 12.09. abends als Pruefstein.

    Von 21 Beobachtungen waren 17 Rauschen, davon zwoelf Zeilen smartscreen.
    Die Regel dagegen stand schon im Haus - fuer genau einen Dienst, per Name.
    """
    print("\nzwoelf Zeilen smartscreen: wer kommt und geht, ist Bedarfsdienst")
    jetzt = time.time()
    GRUND = zustand()["namen"]
    SM = {"name": "smartscreen", "anzahl": 1, "seit": jetzt - 300}

    def blick(vorher, namen):
        neu = haus._bestaetigt(vorher, zustand(namen=list(namen)))
        return neu, haus.veraenderungen(vorher, neu)

    # Ausgangslage, ohne smartscreen. Der erste Blick vergleicht nicht.
    stand = haus._bestaetigt({"namen": [], "namen_roh": []}, zustand())

    alle = []
    # Ein ganzer Umlauf: zweimal da (Entprellung), zweimal weg.
    for namen in (GRUND + [SM], GRUND + [SM], GRUND, GRUND):
        stand, zeilen = blick(stand, namen)
        alle += zeilen
    pruefe(len(alle) == 2, "ein Umlauf kostet genau zwei Zeilen: %s" % alle)
    pruefe(alle[0] == "smartscreen laeuft, seit %s."
           % haus._uhr(SM["seit"]),
           "die erste ist die Meldung: %s" % alle[0])
    pruefe("kommt und geht von selbst" in alle[1]
           and "melde es nicht mehr" in alle[1],
           "die zweite ist die Erkenntnis, nicht 'laeuft nicht mehr': %s"
           % alle[1])
    pruefe(stand["namen_bedarf"].get("smartscreen"),
           "und sie steht im Zustand, nachlesbar: %s"
           % list(stand["namen_bedarf"]))

    # Und ab jetzt: Ruhe. Fuenf weitere Umlaeufe, wie an einem Edge-Vormittag.
    still = []
    for i in range(5):
        # Jedes Mal eine neue Startzeit - auch der Neustart darf nichts melden.
        sm = {"name": "smartscreen", "anzahl": 1, "seit": jetzt - 300 + i * 120}
        for namen in (GRUND + [sm], GRUND + [sm], GRUND, GRUND):
            stand, zeilen = blick(stand, namen)
            still += zeilen
    pruefe(still == [], "fuenf weitere Umlaeufe, kein Wort: %s" % still)

    print("\nund der Neustarter: msedge, OneDrive.Sync.Service")
    stand = haus._bestaetigt({"namen": [], "namen_roh": []}, zustand())
    zeilen_alle = []
    for i in range(1, 6):
        # Derselbe Name bleibt da, nur die aelteste Startzeit springt nach
        # vorn - so sieht ein neu gestarteter Unterprozess aus.
        e = {"name": "msedge", "anzahl": 5, "seit": jetzt - 3600 + i * 600}
        stand, zeilen = blick(stand, GRUND + [e])
        zeilen_alle += zeilen
    erkenntnis = [z for z in zeilen_alle if "Bedarfsdienst" in z]
    pruefe(not [z for z in zeilen_alle if "neu gestartet" in z],
           "kein einziges 'wurde neu gestartet': %s" % zeilen_alle)
    pruefe(len(erkenntnis) == 1,
           "beim ERSTEN Neustart schon die Erkenntnis - das Auftauchen war "
           "der erste Wechsel, der Neustart ist der zweite: %s" % erkenntnis)
    pruefe(len(zeilen_alle) == 2,
           "fuenf Neustarts, zwei Zeilen (Auftauchen, Erkenntnis): %s"
           % zeilen_alle)

    print("\nwas einmal kommt und bleibt, wird weiter gemeldet")
    stand = haus._bestaetigt({"namen": [], "namen_roh": []}, zustand())
    neu = {"name": "SwarmUI", "anzahl": 1, "seit": jetzt - 300}
    gesagt = []
    for namen in (GRUND + [neu], GRUND + [neu], GRUND + [neu], GRUND + [neu]):
        stand, zeilen = blick(stand, namen)
        gesagt += zeilen
    pruefe(gesagt == ["SwarmUI laeuft, seit %s." % haus._uhr(neu["seit"])],
           "ein Programm, das startet und laeuft, bleibt eine Meldung: %s"
           % gesagt)
    pruefe("SwarmUI" not in stand["namen_bedarf"],
           "und wird nicht zum Bedarfsdienst")

    print("\ndas Fenster ist ein Tag, die Erkenntnis bleibt")
    # Ein Wechsel von vorgestern zaehlt nicht mehr mit.
    gestern = {"namen": GRUND, "namen_roh": GRUND,
               "namen_wechsel": {"alt": [jetzt - 50 * 3600],
                                 "frisch": [jetzt - 3600]},
               "namen_bedarf": {}}
    w, b = haus._bedarf_zaehlen(gestern, set(), set(), set(), erster=False)
    pruefe("alt" not in w and w.get("frisch") == [jetzt - 3600],
           "ein Wechsel von vor 50 Stunden ist vergessen: %s" % list(w))
    pruefe(b == {}, "und loest keine Einordnung aus")
    # Die Einordnung selbst verfaellt nicht.
    lang = {"namen": GRUND, "namen_roh": GRUND, "namen_wechsel": {},
            "namen_bedarf": {"smartscreen": jetzt - 50 * 3600}}
    w, b = haus._bedarf_zaehlen(lang, set(), set(), set(), erster=False)
    pruefe("smartscreen" in b,
           "was er begriffen hat, behaelt er - sonst kaeme smartscreen jeden "
           "Tag einmal durch: %s" % b)

    print("\nund unsere eigenen Werkzeuge werden nicht einmal eingeordnet")
    stand = haus._bestaetigt({"namen": [], "namen_roh": []}, zustand())
    t = {"name": "tail", "anzahl": 1, "seit": jetzt - 300, "unser": True}
    unsers = []
    for namen in (GRUND + [t], GRUND + [t], GRUND, GRUND):
        stand, zeilen = blick(stand, namen)
        unsers += zeilen
    pruefe(unsers == [],
           "unser tail kommt und geht, ohne eine Zeile: %s" % unsers)


def probe_unser_ort() -> None:
    print("\nwoher ein Programm kommt, wird gemessen, nicht geraten")
    orte = haus._unsere_orte()
    pruefe(orte, "es gibt Orte: %s" % len(orte))
    pruefe(all(len(Path(o).parts) >= 3 for o in orte),
           "keiner ist so kurz, dass er das halbe Laufwerk umfasst: %s"
           % [o for o in orte if len(Path(o).parts) < 3])
    pruefe(all(o == o.lower() for o in orte),
           "alle klein geschrieben - PowerShell vergleicht klein")
    pruefe(any("mcp-test" in o for o in orte), "das Projekt ist dabei")
    pruefe(any("git" in o for o in orte),
           "und die Git-Installation, in der tail, grep und sed stecken: %s"
           % [o for o in orte if "git" in o])

    ps = haus._orte_fuer_ps()
    pruefe(ps.count("'") == 2 * len(orte) and "," in ps,
           "als PowerShell-Liste mit einfachen Anfuehrungszeichen: %s" % ps)

    # Der Unterschied zwischen Ort und Name.
    pruefe(haus._unser({"name": "tail", "unser": True}, "tail"),
           "am Ort erkannt, obwohl tail in keiner Liste steht")
    pruefe(not haus._unser({"name": "tail"}, "tail"),
           "ohne Ortsmessung ist tail unbekannt - deshalb musste der Ort her")
    pruefe(haus._unser({"name": "pythonw3.10"}, "pythonw3.10"),
           "der Name bleibt als Rueckfall, wenn Windows den Pfad verweigert")
    pruefe(not haus._unser({"name": "msedge", "unser": False}, "msedge"),
           "und msedge ist nicht unser")


def probe_dienste() -> None:
    print("\nDienste")
    alt = zustand()
    a = haus.veraenderungen(alt, zustand(
        dienste={"sollen_aber_aus": ["Spooler"]}))
    pruefe(len(a) == 1 and "Spooler" in a[0] and "tut es" in a[0],
           "ein Dienst, der laufen soll und nicht laeuft: %s" % a)
    a = haus.veraenderungen(
        zustand(dienste={"sollen_aber_aus": ["Spooler"]}), zustand())
    pruefe(len(a) == 1 and "wieder" in a[0],
           "und wenn er wiederkommt, auch das: %s" % a)
    pruefe(haus.veraenderungen(
        zustand(dienste={"sollen_aber_aus": ["Spooler"], "aus_roh": None}),
        zustand()) == [],
        "ohne Rohmessung im Vorher kein Vergleich - der Umstieg auf die "
        "Entprellung meldet nicht das ganze Haus")


def probe_dienste_entprellt() -> None:
    print("\nder Updater, der eine Minute lebt (die vier Zeilen von 12:05)")
    G = "GoogleUpdaterService152.0.7933.0"

    def blick(vorher, aus):
        """Eine Messung: roh gemessen, entprellt, verglichen."""
        neu = haus._dienste_bestaetigt(
            vorher, zustand(dienste={"sollen_aber_aus": list(aus)}))
        return neu, haus.veraenderungen(vorher, neu)

    # Ausgangslage: der Updater steht seit jeher auf "soll, tut aber nicht" -
    # das ist sein Normalzustand, nicht sein Fehler.
    stand, _ = blick(zustand(dienste={"aus_roh": None}), [G])
    pruefe(stand["dienste"]["sollen_aber_aus"] == [G]
           and stand["dienste"]["aus_roh"] == [G],
           "der erste Blick stellt fest: %s" % stand["dienste"])

    # 12:05:56 - der Updater startet und laeuft eine Minute.
    stand, zeilen = blick(stand, [])
    pruefe(zeilen == [], "er laeuft los: keine Zeile (%s)" % zeilen)
    # 12:06:58 - er ist wieder weg.
    stand, zeilen = blick(stand, [G])
    pruefe(zeilen == [], "er hoert wieder auf: keine Zeile (%s)" % zeilen)
    pruefe(stand["dienste"]["sollen_aber_aus"] == [G],
           "und der bestaetigte Zustand hat sich nie bewegt")

    print("\nein Updater, der lange genug laeuft, um die Entprellung zu "
          "ueberstehen")
    # Drei Messungen lang laufend - das ueberlebt zwei Blicke.
    stand, z1 = blick(stand, [])
    stand, z2 = blick(stand, [])
    pruefe(z1 == [] and any("laeuft wieder" in z for z in z2),
           "beim zweiten Blick heisst es 'laeuft wieder': %s" % z2)
    stand, z3 = blick(stand, [G])
    stand, z4 = blick(stand, [G])
    pruefe(any("Bedarfsdienst" in z for z in z4)
           and not any("tut es aber nicht" in z for z in z4),
           "der zweite Wechsel macht ihn zum Bedarfsdienst, statt ihn zu "
           "melden: %s" % z4)
    pruefe(stand["dienste"]["bedarf"] == [G],
           "und das steht im Zustand, nachlesbar: %s" % stand["dienste"])

    # Ab jetzt schweigt er ueber ihn, so oft er auch kommt und geht.
    still = []
    for aus in ([], [], [G], [G], [], []):
        stand, zeilen = blick(stand, aus)
        still += zeilen
    pruefe(still == [],
           "und danach kein Wort mehr ueber ihn, sechs Blicke lang: %s"
           % still)

    print("\nein Dienst, der wirklich ausfaellt, wird trotzdem gemeldet")
    stand = zustand(dienste={"aus_roh": []})
    stand, z1 = blick(stand, ["Spooler"])
    stand, z2 = blick(stand, ["Spooler"])
    pruefe(z1 == [] and any("Spooler" in z and "tut es aber nicht" in z
                            for z in z2),
           "einmal gesehen reicht nicht, beim zweiten Blick steht es da: "
           "%s / %s" % (z1, z2))
    stand, z3 = blick(stand, ["Spooler"])
    pruefe(z3 == [], "und danach nicht noch einmal: %s" % z3)


def probe_satz() -> None:
    print("\nAuskunft ohne Modell")
    s = haus.satz(zustand())
    pruefe("16 Kerne" in s and "61.6" in s and "36 Grad" in s,
           "ein Satz mit Kernen, Speicher, Grafikkarte: %s" % s)
    pruefe("1 Tag," in s or "1 Tag." in s,
           "und richtiger Einzahl - nicht \"1 Tagen\": %s" % s)
    pruefe("chrome mit 500 MB" in haus.groesste(zustand()),
           "wer den Speicher belegt")
    pruefe("nicht messen" in haus.satz({}),
           "ohne Messung sagt er das, statt etwas zu erfinden")


def probe_speicher_sprechform() -> None:
    """Der Mangel, den der Mac am 12.09. gemessen hat.

    Die echte Antwort war: "Am meisten Speicher belegen Memory Compression
    mit 1394 MB, llama-server mit 1073 MB, explorer mit 790 MB, llama-server
    mit 643 MB, chrome mit 565 MB." Fuenf Posten, und llama-server zweimal -
    zusammen 1716 MB, also mehr als Memory Compression. Die Antwort war
    nicht nur lang, sie nannte den Zweitgroessten zuerst.
    """
    print("\nSpeicherfrage - zwei Namen, zusammengezaehlt")
    # Genau die Lage des Mac, nachgebaut.
    echt = zustand(prozesse=[
        {"name": "Memory Compression", "pid": 1, "ram_mb": 1394},
        {"name": "llama-server", "pid": 2, "ram_mb": 1073},
        {"name": "explorer", "pid": 3, "ram_mb": 790},
        {"name": "llama-server", "pid": 4, "ram_mb": 643},
        {"name": "chrome", "pid": 5, "ram_mb": 565},
    ])

    zus = haus.nach_namen(echt)
    pruefe(zus[0]["name"] == "llama-server" and zus[0]["anzahl"] == 2,
           "zusammengezaehlt ist llama-server der groesste, nicht der zweite: "
           "%s mit %.0f MB" % (zus[0]["name"], zus[0]["ram_mb"]))
    pruefe(abs(zus[0]["ram_mb"] - 1716) < 1,
           "1073 + 643 = 1716 MB: %.0f" % zus[0]["ram_mb"])

    a = haus.antwort("Wer belegt den meisten Speicher?", echt)
    pruefe(a.count("llama-server") == 1,
           "der Name steht nur einmal in der Antwort: %s" % a)
    pruefe("1,7 GB" in a,
           "als Groessenordnung, nicht als vierstellige MB-Zahl: %s" % a)
    pruefe("in zwei Prozessen" in a,
           "und die zusammengezaehlte Zahl gibt sich als solche zu erkennen")
    namen = sum(1 for n in ("Memory Compression", "llama-server", "explorer",
                            "chrome") if n in a)
    pruefe(namen == 2, "genau zwei Namen, nicht fuenf (%d): %s" % (namen, a))
    # Keine Zahl der uebrigen: `prozesse` ist die Bestenliste der zwoelf
    # groessten, eine Restzahl klaenge wie eine Gesamtzahl.
    pruefe("weitere sind kleiner" not in a,
           "keine Restzahl, die wie eine Gesamtzahl klingt: %s" % a)
    pruefe(len(a.split()) <= 24,
           "und kurz genug zum Vorlesen (%d Woerter): %s" % (len(a.split()), a))

    # Ein einzelner Prozess bekommt keinen Prozess-Zusatz.
    einer = haus.antwort("Wer belegt den meisten Speicher?", zustand())
    pruefe("in ein" not in einer,
           "bei einem einzigen Prozess kein Zusatz: %s" % einer)


def probe_datei() -> None:
    print("\nVorher und Nachher auf der Platte")
    ort = probenort.ablage("haus")
    try:
        p = ort / "haus.json"
        pruefe(haus.lesen(p) == {}, "keine Datei, kein Vorher, keine Ausnahme")
        haus.schreiben(zustand(), p)
        pruefe(haus.lesen(p)["maschine"]["cpu_kerne"] == 16,
               "geschrieben und wiedergelesen")
        p.write_text("{kaputt", encoding="utf-8")
        pruefe(haus.lesen(p) == {},
               "eine halb geschriebene Datei ist kein Vorher")
    finally:
        probenort.wegraeumen(ort)


def probe_gegenstand() -> None:
    print("\nworum es in einer Windows-Meldung geht")
    faelle = [
        ("Fehlerhafter Anwendungsname: llama-server.exe, Version: 0.0.0.0, "
         "Zeitstempel: 0x1234", "llama-server.exe"),
        ("Faulting application name: chrome.exe, version: 1.2",
         "chrome.exe"),
        # Der Fall, der beim ersten Lauf schiefging: Produktnamen enthalten
        # Punkte, und bis zum ersten Punkt zu lesen machte aus
        # siebenundvierzig Paketen ein einziges namens "Microsoft".
        ("Das Produkt wurde durch Windows Installer installiert. "
         "Produktname: Microsoft .NET Runtime - 8.0.31 (x64). "
         "Produktversion: 8.0.31. Produktsprache: 1033.",
         "Microsoft .NET Runtime - 8.0.31 (x64)"),
        ("Das Produkt wurde durch Windows Installer entfernt. "
         "Produktname: AMD Settings. Produktversion: 2026.07. ",
         "AMD Settings"),
        ("Der Dienst \"Spooler\" wurde unerwartet beendet.", "Spooler"),
        ("Die Richtliniendefinition ist doppelt vorhanden.", ""),
    ]
    for text, erwartet in faelle:
        pruefe(haus._gegenstand(text) == erwartet,
               "%r -> %r" % (text[:52], haus._gegenstand(text)))


def probe_programme() -> None:
    print("\nwas installiert, entfernt, aktualisiert wurde")
    jetzt = [{"name": "AnyDesk", "fassung": "9.0.14"},
             {"name": "Steam", "fassung": "2.10"}]
    pruefe(haus.programm_unterschiede([], jetzt) == [],
           "ohne Vorher zaehlt er nicht alle 121 Programme auf")
    pruefe(haus.programm_unterschiede(jetzt, jetzt) == [],
           "unveraendert ist unveraendert")
    a = haus.programm_unterschiede(
        [{"name": "Steam", "fassung": "2.10"}], jetzt)
    pruefe(a == ["AnyDesk wurde installiert, Fassung 9.0.14."],
           "neu installiert: %s" % a)
    a = haus.programm_unterschiede(
        jetzt + [{"name": "Altes", "fassung": "1.0"}], jetzt)
    pruefe(a == ["Altes wurde deinstalliert."], "entfernt: %s" % a)
    a = haus.programm_unterschiede(
        [{"name": "AnyDesk", "fassung": "9.0.13"},
         {"name": "Steam", "fassung": "2.10"}], jetzt)
    pruefe(a == ["AnyDesk wurde von Fassung 9.0.13 auf 9.0.14 aktualisiert."],
           "aktualisiert, nicht neu installiert: %s" % a)
    a = haus.programm_unterschiede(
        [{"name": "AnyDesk", "fassung": None},
         {"name": "Steam", "fassung": "2.10"}], jetzt)
    pruefe(a == [],
           "eine fehlende Fassung ist kein Update - sonst meldet jedes "
           "Programm ohne Versionsangabe eine Aenderung")


def echt_ereignisse() -> None:
    print("\n" + "=" * 70)
    print("Das Windows-Ereignisprotokoll, nur lesend")
    print("=" * 70)
    t0 = time.time()
    e = haus.ereignisse(48)
    dauer = round(time.time() - t0, 1)
    arten = {}
    for x in e:
        arten[x["art"]] = arten.get(x["art"], 0) + 1
    print(f"  {len(e)} Ereignisse aus 48 Stunden in {dauer} s: {arten}")
    pruefe(dauer < 20, "das Protokoll zu lesen dauert %s s" % dauer)
    pruefe(all(x.get("ts") for x in e), "jedes Ereignis hat einen Zeitpunkt")
    pruefe(sum(1 for x in e if x["art"] == "installiert"
               and not x["gegenstand"]) <= 2,
           "fast jede Installationsmeldung nennt ihr Produkt")
    for x in e:
        if x["art"] in ("neustart", "absturz", "anmeldung"):
            print(f"    {time.strftime('%d.%m %H:%M', time.localtime(x['ts']))}"
                  f"  {x['was']}")
    t0 = time.time()
    p = haus.programme()
    print(f"\n  {len(p)} installierte Programme in "
          f"{round(time.time() - t0, 1)} s")
    pruefe(len(p) > 20, "die Programmliste ist da")


def echt_messen() -> None:
    print("\n" + "=" * 70)
    print("Zweimal wirklich messen")
    print("=" * 70)
    t0 = time.time()
    eins = haus.bild()
    d1 = round(time.time() - t0, 1)
    pruefe(bool(eins.get("maschine", {}).get("cpu_kerne")),
           "die Maschine wurde gemessen (%s Kerne, %s s)"
           % (eins.get("maschine", {}).get("cpu_kerne"), d1))
    pruefe(len(eins.get("namen") or []) > 50,
           "%d Prozessnamen" % len(eins.get("namen") or []))
    pruefe(bool(eins.get("gpu", {}).get("name")),
           "die Grafikkarte: %s, %s Prozent, %s Grad"
           % (eins.get("gpu", {}).get("name"),
              eins.get("gpu", {}).get("last_prozent"),
              eins.get("gpu", {}).get("temperatur_c")))
    pruefe(d1 < 10, "eine Messung dauert %s s - das geht jede Minute" % d1)

    zwei = haus.bild()
    a = haus.veraenderungen(eins, zwei)
    print(f"\n  zwei Messungen kurz hintereinander -> "
          f"{len(a)} Veraenderungen")
    for z in a:
        print(f"    {z}")
    pruefe(len(a) <= 3,
           "zwei Messungen in derselben Sekunde ergeben fast nichts - "
           "sonst waere die Stufung zu fein")
    print(f"\n  {haus.satz(zwei)}")
    print(f"  groesste: {haus.groesste(zwei)}")
    print(f"  Zustandsdatei waere {len(json.dumps(zwei, ensure_ascii=False))} "
          f"Zeichen gross")


def main() -> int:
    print("Probe haus")
    probe_erster_blick()
    probe_rauschen()
    probe_echte_veraenderung()
    probe_prozesse()
    probe_unsere_werkzeuge()
    probe_bestaetigt()
    probe_bedarf_namen()
    probe_unser_ort()
    probe_dienste()
    probe_dienste_entprellt()
    probe_satz()
    probe_speicher_sprechform()
    probe_gegenstand()
    probe_programme()
    probe_datei()
    if "--echt" in sys.argv:
        echt_messen()
        echt_ereignisse()
    print("\n%d von %d bestanden" % (GESAMT - FEHLER, GESAMT))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
