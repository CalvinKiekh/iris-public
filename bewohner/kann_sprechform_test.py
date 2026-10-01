"""Misst die Sprechform der Faehigkeitsantwort - mehrfach, nicht einmal.

    python -X utf8 kann_sprechform_test.py            5 Laeufe
    python -X utf8 kann_sprechform_test.py --n=10     mehr

WARUM DIESE PROBE EXISTIERT: Am 12.09. habe ich die Anweisung in kann.block()
dreimal nachgeschaerft und jedes Mal an EINEM Lauf gemessen. Dieselbe
Anweisung lieferte:

    39 Woerter, keine Doppelung, drei Beispiele
    37 Woerter, Satz 1 als Fuenferliste, Doppelung
    29 Woerter, Satz 1 als Fuenferliste, Doppelung

Ich habe also Rauschen hinterhergebaut und zweimal eine Verschlechterung fuer
eine Verbesserung gehalten. verbot_test.py sagt es seit heute frueh:
"Bei einem einzigen Durchlauf schwankte dieselbe Lage zwischen 0 von 4 und
3 von 4 - eine Zahl aus einem Versuch sagt hier nichts."

Gemessen wird, was der Mac beanstandet hat, als ZAHLEN:

    woerter      wie lang (er nannte 34 als zu lang)
    posten_s1    Aufzaehlungsglieder im ersten Satz (mehr als 2 = Katalog)
    verben_s1    Taetigkeitswoerter im ersten Satz - weil posten_s1
                 ausgehebelt wurde, indem das Modell die Kommas wegliess
                 und die Liste behielt
    doppelung    steht dieselbe Sache in Satz 1 UND Satz 2?
    zahl         kommt eine Anzahl vor ("27 Faehigkeiten")?

UND DIE WICHTIGSTE REGEL DIESER PROBE: Die Antwort steht in jeder Zeile mit
da. Die Zahlen sind zum Vergleichen, nicht zum Urteilen. Am 12.09. wurden
alle vier Zahlen besser (Doppelung von 5/5 auf 0/5, Posten von 4,6 auf 1,4)
und die Antworten dabei schlechter: "Ich bin ein Beobachter, Verarbeiter und
Helfer." Wer nur auf die Zusammenfassung sieht, optimiert das Mass.

Geschrieben wird nichts: kein Journal, keine Datei, keine Stimme.
"""
from __future__ import annotations

import re
import sys
import threading
from pathlib import Path

HIER = Path(__file__).resolve().parent
FRAGE = "Was kannst du alles?"

# Woran eine Doppelung erkannt wird: dieselbe Sache in zwei Saetzen. Nicht am
# ganzen Wort - "Bildschirm" steht in "beobachte den Bildschirm" und in "sehe
# den Bildschirm an", und genau das hat der Mac gemeldet.
SACHEN = ("bildschirm", "heimnetz", "netz", "termin", "stimme", "rückblick",
          "rueckblick", "protokoll", "gedächtnis", "gedaechtnis", "werkzeug",
          "ansprech", "erinner")


def messen(antwort: str) -> dict:
    saetze = [s.strip() for s in re.split(r"(?<=[.!?])\s+", antwort)
              if s.strip()]
    s1 = saetze[0] if saetze else ""
    rest = " ".join(saetze[1:])

    # Aufzaehlungsglieder im ersten Satz: Kommas plus " und ".
    #
    # ACHTUNG, DIESES MASS IST AUSHEBELBAR, und es ist am 12.09. ausgehebelt
    # worden. Als die Anweisung "keine Aufzaehlung mit Kommas" verlangte, kam
    # zurueck: "Ich beobachte den Bildschirm vermerke wer im Heimnetz ist
    # pruefe ob ich sprechen darf fuehre naechtliche Protokolle und erinnere
    # an Termine." Dieselbe Fuenferliste, nur ohne Kommas - gezaehlt EIN
    # Posten. Die Zahl wurde besser, die Antwort schlechter.
    #
    # Deshalb steht die Antwort in jeder Zeile mit da, und deshalb ist die
    # Zusammenfassung unten kein Urteil. Wer nur auf die Zahlen sieht,
    # optimiert das Mass statt der Sache.
    posten = s1.count(",") + len(re.findall(r"\bund\b", s1))
    # Gegen genau diesen Trick: Taetigkeitswoerter in der ersten Person
    # zaehlen, ohne Satzzeichen zu brauchen.
    verben = len(re.findall(r"\b(beobachte|vermerke|pruefe|prüfe|fuehre|"
                            r"führe|erinnere|melde|sehe|sage|hoere|höre|"
                            r"merke|entscheide|erstelle|verfolge|verarbeite|"
                            r"analysiere|antworte|kommuniziere)\b",
                            s1, re.IGNORECASE))

    in_s1 = {w for w in SACHEN if w in s1.lower()}
    in_rest = {w for w in SACHEN if w in rest.lower()}
    doppelt = sorted(in_s1 & in_rest)

    zahl = bool(re.search(r"\b\d{1,3}\b", antwort)
                or re.search(r"\b(siebenundzwanzig|insgesamt\s+\w+\s+"
                             r"(f(ä|ae)higkeiten|dinge))\b", antwort, re.I))
    return {"woerter": len(antwort.split()), "saetze": len(saetze),
            "posten_s1": posten, "verben_s1": verben, "doppelung": doppelt, "zahl": zahl,
            "antwort": antwort}


def einmal() -> str:
    from gespraech import Gespraech
    probe = HIER / "werkstatt" / "_sprechform_probe"
    probe.mkdir(exist_ok=True)
    g = Gespraech(probe, lambda *a, **k: None, Path("nicht-da.wav"))
    n = g._antwort_holen(FRAGE, {"state": "wach"}, {"vorgaenge": []},
                         nur_bauen=True)
    saetze: list = []
    g._abbruch = threading.Event()
    g._antwort_stroemen(n, saetze, threading.Event())
    return " ".join(s.strip() for s in saetze).strip()


def main() -> int:
    wie_oft = 5
    for a in sys.argv[1:]:
        if a.startswith("--n="):
            wie_oft = int(a.split("=", 1)[1])

    print("Sprechform der Faehigkeitsantwort, %d Laeufe" % wie_oft)
    print("Frage: %r\n" % FRAGE)
    ergebnisse = []
    for i in range(wie_oft):
        a = einmal()
        m = messen(a)
        ergebnisse.append(m)
        print("%2d. %3d Woerter, %d Saetze, Satz 1: %d Posten / %d Verben, "
              "Doppelung %-22s Zahl %s"
              % (i + 1, m["woerter"], m["saetze"], m["posten_s1"],
                 m["verben_s1"], ",".join(m["doppelung"]) or "-",
                 "JA" if m["zahl"] else "-"))
        print("    %s" % a[:150])

    if not ergebnisse:
        return 1
    n = len(ergebnisse)
    print("\n" + "=" * 66)
    print("  Woerter        Schnitt %.0f, von %d bis %d"
          % (sum(e["woerter"] for e in ergebnisse) / n,
             min(e["woerter"] for e in ergebnisse),
             max(e["woerter"] for e in ergebnisse)))
    print("  Posten Satz 1  Schnitt %.1f, hoechstens %d  (aushebelbar!)"
          % (sum(e["posten_s1"] for e in ergebnisse) / n,
             max(e["posten_s1"] for e in ergebnisse)))
    print("  Verben Satz 1  Schnitt %.1f, hoechstens %d  (braucht keine "
          "Satzzeichen)"
          % (sum(e["verben_s1"] for e in ergebnisse) / n,
             max(e["verben_s1"] for e in ergebnisse)))
    print("  Doppelung      %d von %d Laeufen"
          % (sum(1 for e in ergebnisse if e["doppelung"]), n))
    print("  Anzahl genannt %d von %d Laeufen"
          % (sum(1 for e in ergebnisse if e["zahl"]), n))
    print("=" * 66)
    print("\nSo wird verglichen, nicht nach Gefuehl. Eine Aenderung an der\n"
          "Anweisung ist besser, wenn DIESE Zahlen besser werden - nicht,\n"
          "wenn ein einzelner Lauf gefaellig klingt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
