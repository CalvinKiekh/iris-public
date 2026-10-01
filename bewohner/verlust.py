"""Was fehlt - festgehalten, nicht nachgebaut.

    python -X utf8 verlust.py        zeigt es
    python -X utf8 verlust.py --md   schreibt werkstatt\\VERLOREN.md

Am 12.09. gegen 21:00 hat eine Probe `werkstatt\\` geloescht. Die Spiegelung
hat das meiste zurueckgebracht, zwei Dateien aber nicht - sie waren nie darin:

    ERINNERUNG.md       Calvins Kernwissen, das in JEDEN Prompt mitgeht
    erinnerungen.json   die Termine

WARUM ES DIESE DATEI GIBT, statt eines Satzes in einem Commit: Beide fehlen
LEISE. `gedaechtnis.kernwissen()` gibt bei fehlender Datei "" zurueck, und
`erinnern.lesen()` eine leere Liste - das sieht aus wie "nichts eingetragen"
und nicht wie "verloren". Ein Verlust, den man nicht sieht, ist schlimmer als
einer, der sich meldet.

UND SIE WIRD ERZEUGT, nicht von Hand geschrieben: Legt Calvin die Dateien neu
an, verschwindet der Eintrag beim naechsten Lauf von allein. Eine Notiz, die
nicht mitwaechst, ist nach einer Woche eine Falschaussage.

NACHGEBAUT WIRD NICHTS. Was in ERINNERUNG.md stand, weiss ich nicht; aus dem
geretteten Log sind drei Fakten zurueck (Lena Marie, die Bruecke zum Mac, wo er
wohnt), und die stehen im Gedaechtnis. Mehr zu schreiben waere Erfinden.
"""
from __future__ import annotations

from einstellungen import NAME, NAMENS
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
BERICHT = WERKSTATT / "VERLOREN.md"

# DIE TRAGENDEN DATEIEN. Fehlt eine, ist die Antwort auf eine Frage nicht
# falsch, sondern LEER - und das sieht aus wie ein Normalzustand. Genau dieser
# Fehlertyp hat uns am 12.09. zweimal getroffen:
#
#   "Habe ich Termine?"        -> "nein"   statt "meine Liste fehlt seit 21 Uhr"
#   "Was weisst du ueber X?"   -> nichts   statt "mein Gedaechtnis fehlt"
#
# Der zweite Satz ist die Wahrheit, der erste eine Falschaussage. Darum steht
# hier, welche Dateien tragen, und `satz()` gibt es in jeden Prompt.
TRAGEND = (
    ("Terminliste", lambda w: w / "werkzeuge" / "erinnerungen.json",
     "Ich habe keine Terminliste - die Datei fehlt seit dem 12.09. gegen "
     f"21 Uhr. Sag NICHT, dass keine Termine vorliegen: Was {NAME} vorher "
     "genannt hat, ist verloren, und das ist ein Unterschied."),
    ("Kernwissen", lambda w: w / "ERINNERUNG.md",
     "Mein Kernwissen (ERINNERUNG.md) fehlt seit dem 12.09. gegen 21 Uhr. "
     "Was immer gelten sollte, steht mir nicht zur Verfuegung - sag das, "
     "statt so zu tun, als gaebe es nichts zu wissen."),
    ("Gedaechtnis", lambda w: w / "gedaechtnis.db",
     "Meine Gedaechtnisdatenbank fehlt. Finde ich nichts, heisst das nicht "
     "'darueber weiss ich nichts', sondern 'ich kann gerade nicht "
     "nachsehen'."),
    ("Chronik", lambda w: w / "journal.jsonl",
     "Das Journal fehlt. Auf 'was ist letzte Nacht passiert' kann ich nicht "
     "antworten - nicht weil nichts passiert ist, sondern weil die "
     "Aufzeichnung weg ist."),
    ("Gespraechsverlauf", lambda w: w / "sitzungen.jsonl",
     "Die Sitzungsliste fehlt. 'Worueber haben wir geredet' ist damit nicht "
     "beantwortbar - der Wortlaut ist weg, nicht das Gespraech."),
)


def tragend_fehlt(werkstatt: Path | None = None) -> list[tuple[str, str]]:
    """[(Name, Satz fuer den Prompt)] - was tragend ist und fehlt."""
    w = werkstatt or WERKSTATT
    return [(name, satz) for name, pfad, satz in TRAGEND if not pfad(w).exists()]


def satz(werkstatt: Path | None = None) -> str:
    """Was in JEDEN Prompt gehoert, solange etwas Tragendes fehlt.

    Lieber sagen, dass etwas fehlt, als so tun, als gaebe es nichts. Eine
    leere Antwort auf eine Frage nach Terminen ist eine Falschaussage, wenn
    die Liste verlorengegangen ist.
    """
    fehlt = tragend_fehlt(werkstatt)
    if not fehlt:
        return ""
    return ("WICHTIG - es fehlt etwas, und das musst du sagen, wenn es zur "
            "Frage passt:\n" + "\n".join(f"- {s}" for _, s in fehlt))


# Was fehlen KANN, ohne dass es auffaellt - mit dem, was dann nicht mehr geht.
WICHTIG = (
    ("ERINNERUNG.md", WERKSTATT / "ERINNERUNG.md",
     f"{NAMENS} Kernwissen. Es geht in JEDEN Prompt mit (gedaechtnis."
     "kernwissen()). Fehlt es, antwortet er ohne das, was immer gelten soll - "
     "und merkt es nicht, weil eine fehlende Datei wie eine leere aussieht."),
    ("erinnerungen.json", WERKSTATT / "werkzeuge" / "erinnerungen.json",
     "Die Termine. Fehlt die Datei, gibt erinnern.lesen() eine leere Liste "
     "zurueck - es sieht aus wie \"keine Termine\" und nicht wie \"Termine "
     "verloren\". Was vor dem 12.09. vorgemerkt war, ist weg."),
    ("platzverlauf.jsonl", WERKSTATT / "platzverlauf.jsonl",
     "Die Messreihe zum Plattenplatz. Nur als LANGE Reihe etwas wert - "
     "\"die Platte fuellt sich seit drei Tagen\" braucht eine Woche Messung. "
     "Sie faengt wieder bei null an."),
    ("rhythmus", WERKSTATT / "rhythmus.jsonl",
     f"Die Messreihe zu {NAMENS} Tagesrhythmus. Ebenso: nur lang ist sie etwas "
     "wert."),
)


def fehlende() -> list[tuple[str, Path, str]]:
    return [(name, pfad, warum) for name, pfad, warum in WICHTIG
            if not pfad.exists()]


def text() -> str:
    fehlt = fehlende()
    zeilen = ["# Was fehlt", "",
              f"Erzeugt von verlust.py, {time.strftime('%d.%m.%Y %H:%M')}. "
              f"Diese Datei wird bei jedem Lauf neu geschrieben - legt {NAME} "
              f"eine fehlende Datei neu an, verschwindet ihr Eintrag von "
              f"allein.", ""]
    if not fehlt:
        zeilen += ["Nichts fehlt. Alle beobachteten Dateien liegen da.", ""]
        return "\n".join(zeilen)

    zeilen += [f"Am 12.09.2026 gegen 21:00 hat eine Probe `werkstatt\\` "
               f"geloescht. Die Spiegelung hat das meiste zurueckgebracht. "
               f"Diese {len(fehlt)} Dateien nicht - sie waren nie darin.", "",
               "**Nachgebaut ist nichts.** Was darin stand, weiss niemand "
               "mehr; etwas hinzuschreiben waere Erfinden.", ""]
    for name, pfad, warum in fehlt:
        zeilen += [f"## {name}", "", f"`{pfad}`", "", warum, ""]
    zeilen += ["---", "",
               "Drei Fakten sind aus `bewohner.log` gerettet und stehen im "
               "Gedaechtnis: dass Lenas voller Name Lena Marie ist, dass die "
               "Bruecke zum Mac laeuft, und auf welchem Rechner er wohnt. "
               "Das ist alles, was belegbar war.", ""]
    return "\n".join(zeilen)


def melden(journal=None) -> list[str]:
    """Einmal sagen, was fehlt. Gibt die Namen zurueck."""
    fehlt = fehlende()
    if fehlt and journal:
        journal("verlust",
                "Es fehlen: " + ", ".join(n for n, _, _ in fehlt)
                + f". Aufgeschrieben in {BERICHT.name}, nachgebaut ist "
                  f"nichts.", nicht_erinnern=True)
    return [n for n, _, _ in fehlt]


def schreiben() -> Path:
    WERKSTATT.mkdir(parents=True, exist_ok=True)
    BERICHT.write_text(text(), encoding="utf-8")
    return BERICHT


def main() -> int:
    fehlt = fehlende()
    print(f"{len(fehlt)} von {len(WICHTIG)} beobachteten Dateien fehlen:\n")
    for name, pfad, _ in WICHTIG:
        marke = "FEHLT" if not pfad.exists() else "da   "
        print(f"  {marke}  {name:22} {pfad}")
    if "--md" in sys.argv:
        print(f"\ngeschrieben: {schreiben()}")
    else:
        print("\nMit --md nach werkstatt\\VERLOREN.md schreiben.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
