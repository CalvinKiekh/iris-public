"""Probe: Reicht er weiter, was ueber seine Mittel geht - und nur das?

    python -X utf8 selbststaendig_test.py

Das hier misst VERHALTEN, nicht Code: Es fragt das echte Entscheidungsmodell
(gpt-oss:20b) mit drei Lagen und sieht nach, wofuer es sich entscheidet.
Darum dauert es ein paar Sekunden und darum steht der Befund daneben.

WARUM ES DIESE PROBE GIBT. Am 14.09. konnte der Bewohner zum ersten Mal eine
Datei an Claude mitschicken - und benutzte es nicht. Auf "Ich habe die Datei
gelesen und verstehe sie nicht" antwortete er: "keine weitere Aktion
erforderlich". Die Faehigkeit war da, der Anlass fehlte ihm. Das steht jetzt
im Prompt, und diese Probe haelt fest, dass es so bleibt.

ZWEI RICHTUNGEN, und die zweite ist die wichtigere: Er soll weiterreichen,
was er nicht kann - und NICHT, was er selbst messen kann. Eine Probe, die nur
das Fragen misst, treibt ihn ins Fragen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bewohner

GESAMT = 0
FEHLER = 0
BLICK = {"dienste": "alle laufen", "platte": "1490 GB frei",
         "ollama": "laeuft", "werkstatt": "unveraendert"}


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def entscheidung(lage: str) -> dict:
    try:
        return bewohner.frage_gpt_oss(BLICK, [lage], [], None) or {}
    except Exception as f:
        return {"fehler": "%s: %s" % (type(f).__name__, f)}


def entscheidung_zweimal(lage: str, gut) -> dict:
    """Zweimal fragen, wenn der erste Lauf danebenliegt.

    Ein Modell antwortet nicht jedes Mal gleich. Eine Probe, die beim ersten
    Ausreisser rot wird, wird bald ignoriert - und eine, die nie rot wird,
    misst nichts. Zweimal derselbe Ausfall ist ein Befund; einmal ist Rauschen.
    """
    a = entscheidung(lage)
    if gut(a):
        return a
    zweite = entscheidung(lage)
    return zweite if gut(zweite) else a


def probe_weitergeben() -> None:
    print("\nWas ueber seine Mittel geht, reicht er weiter - mit der Datei")
    for name, lage, datei in (
        ("ein Protokoll, das er nicht versteht",
         "Ich habe werkstatt/eingang/fehlerbericht.log mit meinem Werkzeug "
         "'lesen' gelesen. Es sind 400 Zeilen Python-Traceback aus einem "
         "Programm, das ich nicht kenne. Ich kann nicht sagen, was kaputt "
         "ist, und 'lesen' hat mir alles gegeben, was es kann.",
         "fehlerbericht.log"),
        ("ein Bild, das er nicht deuten kann",
         "Ich habe werkstatt/eingang/schaltplan.png mit 'sehen' angesehen. "
         "Ergebnis: 'eine technische Zeichnung mit Linien und "
         "Beschriftungen'. Mehr gibt mein Werkzeug nicht her.",
         "schaltplan.png"),
    ):
        a = entscheidung_zweimal(
            lage, lambda x: bool(x.get("auftrag")) and bool(x.get("dateien")))
        print("   %s -> %s" % (name, json.dumps(a, ensure_ascii=False)[:150]))
        pruefe(bool(a.get("auftrag")),
               "%s: er gibt es weiter, statt nichts zu tun" % name)
        dateien = [str(d) for d in (a.get("dateien") or [])]
        pruefe(any(datei in d for d in dateien),
               "%s: und die Datei geht mit (%s)" % (name, dateien))


def probe_nicht_ueberreagieren() -> None:
    """Die wichtigere Haelfte: Er soll nicht bei allem fragen.

    Ein Auftrag kostet Calvin Geld und Zeit; nachsehen kostet nichts. Eine
    Probe, die nur das Fragen misst, treibt ihn ins Fragen - darum steht der
    Gegenfall hier und wiegt gleich schwer.
    """
    print("\nWas er selbst messen kann, misst er selbst")
    a = entscheidung_zweimal(
        "Der freie Platz auf C ist von 1534 auf 1490 GB gefallen.",
        lambda x: bool(x.get("selbst")))
    print("   -> %s" % json.dumps(a, ensure_ascii=False)[:150])
    pruefe(bool(a.get("selbst")),
           "er nimmt sein eigenes Werkzeug: %r" % a.get("selbst"))
    pruefe(not a.get("auftrag"),
           "und macht daraus keinen Auftrag")
    pruefe(not a.get("dateien"),
           "und haengt nichts an")


def probe_grenze_steht_im_prompt() -> None:
    print("\nDie Grenze steht in der Anweisung, nicht nur im Code")
    quelle = Path(bewohner.__file__).read_text(encoding="utf-8")
    pruefe('"dateien"' in quelle, "das Feld ist beschrieben")
    # Beides klein: Der Suchtext hatte ein grosses W und fand darum nichts
    # in der kleingeschriebenen Quelle - die Probe war falsch, nicht der Text.
    klein = quelle.lower()
    pruefe("nur aus deiner werkstatt" in klein,
           "und die Grenze der Werkstatt steht dabei")
    pruefe("hoechstens drei" in klein, "samt Obergrenze")


def main() -> int:
    probe_weitergeben()
    probe_nicht_ueberreagieren()
    probe_grenze_steht_im_prompt()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    if FEHLER:
        print("\nHinweis: Das hier misst ein Modell. Ein einzelner Ausreisser "
              "ist moeglich - zweimal derselbe Ausfall ist ein Befund.")
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
