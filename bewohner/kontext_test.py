"""Was im Prompt steht - und was NICHT drinstehen darf.

Drei Maengel vom 12.09., alle mit derselben Ursache: Eine Auskunft stand
unbedingt in jedem Prompt, und ein Modell, das eine Frage nicht beantworten
kann, greift nach dem Konkretesten, was es findet.

  "Laeuft das schon lange?"   -> "Der Rechner laeuft seit 1 Tag."
                                 Der Bezug war ein Prozess, nicht der Rechner.
  "Schnurpsel wrgl bitte?"    -> "Ich bin wach, habe keine Bremse gesetzt ...
                                 der Rechner laeuft seit zwei Tagen, hat 16
                                 Kerne, nutzt 7 % CPU ..."
                                 Eine Verlesung des Kontext-Woerterbuchs.
  "Wie geht es dir?"          -> "Mir geht es gut, 17:21."
                                 Die Uhrzeit stand als Vorspann in JEDEM Prompt.

Dieselbe Lehre steht seit heute frueh in kann.block(): "Solange kann_kurz
daneben stand, hatte er drei vollstaendige Listen vor sich und las die
laengste ab." Wer eine Auskunft in jeden Prompt legt, bekommt sie in jeder
Antwort.

    python -X utf8 kontext_test.py

Kein Modell, nichts geschrieben - gemessen wird der PROMPT, nicht die Antwort.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import gespraech
import lage

HIER = Path(__file__).resolve().parent
GESAMT = 0
FEHLER = 0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def prompt(frage: str) -> str:
    """Der Prompt, den der Betrieb bauen wuerde - ohne das Modell zu fragen."""
    probe = HIER / "werkstatt" / "_kontext_probe"
    probe.mkdir(exist_ok=True)
    g = gespraech.Gespraech(probe, lambda *a, **k: None, Path("nicht-da.wav"))
    n = g._antwort_holen(frage, {"state": "wach", "brake": None,
                                 "open_task": None},
                         {"vorgaenge": [], "nachgesehen": 27}, nur_bauen=True)
    return "\n".join(str(m.get("content", "")) for m in n)


def probe_netzfrage() -> None:
    """NEU 1: "Wer ist im Heimnetz?" -> "Keine Geraete.", obwohl 14 da sind."""
    print("\ndie Netzfrage - dieselbe Luecke wie in wissen._VERGAENGLICH")
    trifft = [
        "Wer ist im Heimnetz?",
        "Wer ist im Netz?",
        "Wer ist im Netzwerk?",
        "Wer ist gerade im Heimnetz?",
        "Wer ist im WLAN?",
        "Welche Geräte sind im Heimnetz?",
        "Welche Geraete sind da?",
        "Wie viele Geräte sind im Netz?",
        "Wie viele Geraete sind im Netz?",
        "Was ist alles im Heimnetz?",
    ]
    for f in trifft:
        pruefe(lage.NETZFRAGE.search(f), "erkannt: %r" % f)

    for f in ("Wie spät ist es?", "Wie viel Platz ist frei?",
              "Wie heißt meine Tochter?", "Was kannst du?"):
        pruefe(not lage.NETZFRAGE.search(f), "keine Netzfrage: %r" % f)

    # Und der ganze Weg: Die Frage darf das Modell gar nicht erreichen.
    a = gespraech.dienst_antwort("Wer ist im Heimnetz?", HIER / "werkstatt",
                                 {"state": "wach"}, None)
    pruefe(a is not None,
           "der Dienst beantwortet sie selbst, statt sie weiterzugeben")
    if a:
        print("      %s" % a[:140])
        pruefe("kein anderes Gerät" not in a or not lage.lesen().get("netz"),
               "und sagt nicht \"kein Geraet\", wenn Geraete da sind")


def probe_rechnerblock() -> None:
    """NEU 2 und e): Der Zustandssatz nur bei einer Frage nach dem Rechner."""
    print("\nder Zustandssatz steht nicht mehr in jedem Prompt")
    mit = ("Wie viel Arbeitsspeicher ist frei?",
           "Wie lange läuft der Rechner schon?",
           "Wer belegt den meisten Speicher?",
           "Wie warm ist die Grafikkarte?")
    for f in mit:
        p = prompt(f)
        pruefe("mein_rechner" in p,
               "dabei, weil danach gefragt ist: %r" % f)

    ohne = ("Schnurpsel wrgl bitte?", "Läuft das schon lange?",
            "Wie geht es dir?", "Wie heißt meine Tochter?",
            "Wer bist du eigentlich?")
    for f in ohne:
        p = prompt(f)
        pruefe("mein_rechner" not in p,
               "NICHT dabei, danach war nicht gefragt: %r" % f)
        pruefe("groesste_prozesse" not in p,
               "  und die Prozessliste auch nicht: %r" % f)


def probe_uhrzeit() -> None:
    """NEU 3: Die Uhrzeit klebte an Antworten, in die sie nicht gehoert."""
    print("\ndie Uhrzeit nur bei einer Zeitfrage")
    for f in ("Wie spät ist es?", "Welcher Tag ist heute?",
              "Wie viel Uhr ist es?"):
        p = prompt(f)
        pruefe("Es ist jetzt" in p, "Vorspann dabei: %r" % f)

    for f in ("Wie geht es dir?", "Schnurpsel wrgl bitte?",
              "Wie heißt meine Tochter?", "Wer ist im Heimnetz?"):
        p = prompt(f)
        pruefe("Es ist jetzt" not in p,
               "Vorspann NICHT dabei: %r" % f)

    # Und im Systemtext steht keine Uhrzeit mehr als Beispiel.
    pruefe("17:33" not in gespraech.SYSTEM,
           "der Systemtext nennt keine Uhrzeit als Zahlenbeispiel")


def probe_kein_kahlschlag() -> None:
    """Die Gegenprobe: Was gebraucht wird, ist noch da."""
    print("\nwas bleiben MUSS, ist noch da")
    p = prompt("Wie heißt meine Tochter?")
    pruefe("[Lage]" in p, "der Lageblock steht weiter drin")
    pruefe("zustand" in p, "und der Zustand - danach wird gefragt")
    p2 = prompt("Was kannst du?")
    pruefe("GRUPPE A" in p2, "die Faehigkeitsliste bei der Faehigkeitsfrage")
    p3 = prompt("Wer bist du eigentlich?")
    pruefe("[Wer ich bin]" in p3, "der Identitaetsblock bei der Frage nach ihm")
    pruefe("GRUPPE A" not in p3, "und dort NICHT die Faehigkeitsliste")


if __name__ == "__main__":
    print("Probe Prompt-Inhalt")
    probe_netzfrage()
    probe_rechnerblock()
    probe_uhrzeit()
    probe_kein_kahlschlag()
    print("\n%d von %d bestanden" % (GESAMT - FEHLER, GESAMT))
    raise SystemExit(1 if FEHLER else 0)
