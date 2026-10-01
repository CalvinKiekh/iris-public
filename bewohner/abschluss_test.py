"""Probe fuer den Eintragstyp `abschluss` - Punkt 1 aus SKIZZE-UMBAUTEN.md.

    python -X utf8 abschluss_test.py

Gemessen wird dreierlei:

  1. Ein Abschluss OHNE Beleg entsteht nicht. Er waere eine Behauptung, und
     davon hat der Bau genug.
  2. Die Commits kommen an - aber NICHT in der Ich-Form. Calvin und ich haben
     das gebaut, nicht er; aus "Wache gegen stille Luecken gebaut" wird in der
     Ich-Form sofort ein Satz, der die Grenze verschiebt.
  3. Die Obergrenze gilt JE QUELLE. Eine Entwicklungsnacht liefert neun
     Commits, und die duerfen die drei Saetze nicht verdraengen, die von ihm
     handeln - derselbe Fehler wie bei `bestand` mit seinen achtzehn
     Erkenntnissen je Nacht.
"""
from __future__ import annotations

from einstellungen import NAME
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import abschluss
import nacht
import passiert

GESAMT = 0
FEHLER = 0
JETZT = 1789300000.0


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def probe_kein_beleg() -> None:
    print("\nOhne Beleg wird nichts geschrieben")
    zeilen = []
    journal = lambda k, t, **e: zeilen.append((k, t, e))

    pruefe(abschluss.schreiben(journal, "Die Gegenpruefung ist durch",
                               woran="Gegenpruefung",
                               belegt_durch="pruefung.json: 12 geprueft"),
           "mit Beleg: geschrieben")
    pruefe(zeilen and zeilen[0][0] == "abschluss",
           "als Art `abschluss`: %s" % (zeilen[0][0] if zeilen else None))
    pruefe(zeilen and zeilen[0][2].get("belegt_durch")
           == "pruefung.json: 12 geprueft",
           "und der Beleg steht in der Zeile: %s"
           % (zeilen[0][2] if zeilen else None))
    pruefe(zeilen and zeilen[0][2].get("woran") == "Gegenpruefung",
           "woran, auch: %s" % (zeilen[0][2].get("woran") if zeilen else None))

    vorher = len(zeilen)
    pruefe(not abschluss.schreiben(journal, "Ich habe etwas fertig gemacht",
                                   woran="irgendwas", belegt_durch=""),
           "ohne Beleg: nicht geschrieben")
    pruefe(len(zeilen) == vorher,
           "und auch nichts ERSATZWEISE - eine Zeile 'fertig, weiss aber "
           "nicht wodurch' ist genau die Behauptung")
    pruefe(not abschluss.schreiben(journal, "", woran="x", belegt_durch="y"),
           "ohne Text ebenso wenig")
    pruefe(not abschluss.schreiben(None, "Text", "woran", "Beleg"),
           "und ohne Journal wirft es nicht")


def probe_gewicht() -> None:
    print("\nDas Gewicht sitzt zwischen Fund und Entscheidung")
    g = passiert.GEWICHT
    pruefe(g.get("abschluss") is not None,
           "`abschluss` hat ein Gewicht - eine Art ohne Gewicht ist ein Loch")
    pruefe(g["abschluss"] > g["fund"],
           "ueber `fund` (%s > %s)" % (g["abschluss"], g["fund"]))
    pruefe(g["abschluss"] < g["entscheidung"],
           "unter `entscheidung` (%s < %s)"
           % (g["abschluss"], g["entscheidung"]))
    pruefe(g["abschluss"] < g["sitzung"],
           f"und unter `sitzung` - was {NAME} gesagt hat, steht ueber dem, "
           "was ich davon erledigt habe (%s < %s)"
           % (g["abschluss"], g["sitzung"]))
    pruefe("abschluss" in nacht.ARTEN,
           "und die Nacht liest die Art: %s" % (nacht.ARTEN,))


def probe_commits() -> None:
    print("\nDie Commits kommen an, mit Hash als Beleg")

    def falsches_git(befehl, ordner):
        pruefe("--no-merges" in befehl, "ohne Merges gefragt")
        pruefe(any(a.startswith("--since=") for a in befehl),
               "mit einem Zeitraum: %s"
               % [a for a in befehl if a.startswith("--since")])
        return ("fb32422\x1f%d\x1fLeere Bausitzungen kommen vom Kettenstart\n"
                "95c49fe\x1f%d\x1fEine Art ohne Gewicht ist kein Mittelwert\n"
                "\n"
                "kaputt\x1fohne Zeit\n"
                % (JETZT - 600, JETZT - 1200))

    e = abschluss.an_mir(jetzt=JETZT, lauf=falsches_git)
    pruefe(len(e) == 2, "zwei Commits gelesen, die kaputte Zeile faellt weg "
                        "(%d)" % len(e))
    pruefe(e[0]["text"] == "Leere Bausitzungen kommen vom Kettenstart",
           "der neueste zuerst: %s" % e[0]["text"])
    pruefe(e[0]["belegt_durch"] == "Commit fb32422",
           "der Hash ist der Beleg: %s" % e[0]["belegt_durch"])

    # KEINE Ich-Form. Das ist der Kern und nicht die Kosmetik.
    pruefe(all(not t["text"].lower().startswith("ich ") for t in e),
           "kein Satz beginnt mit 'Ich' - sie sind woertlich, nicht "
           "umformuliert: %s" % [t["text"][:40] for t in e])


def probe_grenze_je_quelle() -> None:
    print("\nDie Grenze gilt je Quelle, nicht gemeinsam")
    viele = "\n".join("h%02d\x1f%d\x1fCommit Nummer %d" % (i, JETZT - i * 60, i)
                      for i in range(20))
    e = abschluss.an_mir(jetzt=JETZT, lauf=lambda b, o: viele)
    pruefe(len(e) == abschluss.JE_QUELLE_MAX,
           "zwanzig Commits werden %d: %d"
           % (abschluss.JE_QUELLE_MAX, len(e)))
    pruefe(abschluss.JE_QUELLE_MAX < 10,
           "und die Grenze ist klein genug, dass sie nicht alles verdraengt")

    # Die eigenen Abschluesse haben ihre EIGENE Grenze - sie teilen sie nicht.
    eigene = [{"ts": JETZT - i, "text": "Ich habe Sache %d fertig" % i,
               "belegt_durch": "Probe %d" % i} for i in range(20)]
    pruefe(len(abschluss.saetze(eigene)) == abschluss.JE_QUELLE_MAX,
           "auch die eigenen: %d" % len(abschluss.saetze(eigene)))


def probe_saetze() -> None:
    print("\nDer Beleg steht in der Zeile, nicht nur in der Datei")
    z = abschluss.saetze([{"ts": JETZT, "text": "Die Gegenpruefung ist durch",
                           "belegt_durch": "pruefung.json: 12 geprueft"}])
    pruefe(len(z) == 1 and "Die Gegenpruefung ist durch" in z[0],
           "der Satz steht da: %s" % z)
    pruefe("belegt durch pruefung.json: 12 geprueft" in z[0],
           "und der Beleg daneben: %s" % z[0])
    pruefe(time.strftime("%H:%M", time.localtime(JETZT)) in z[0],
           "mit der Uhrzeit: %s" % z[0])
    pruefe(abschluss.saetze([{"text": "", "belegt_durch": "x"}]) == [],
           "eine leere Zeile gibt keinen Satz")


def probe_git_faellt_aus() -> None:
    print("\nKein git ist kein Fehler des Bewohners")

    def wirft(befehl, ordner):
        raise RuntimeError("fatal: not a git repository")

    pruefe(abschluss.an_mir(jetzt=JETZT, lauf=wirft) == [],
           "dann gibt es diese Quelle heute eben nicht - ohne Absturz")


def main() -> int:
    probe_kein_beleg()
    probe_gewicht()
    probe_commits()
    probe_grenze_je_quelle()
    probe_saetze()
    probe_git_faellt_aus()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
