"""Probe fuer das Verzeichnis des Startbaren.

    python -X utf8 programme_test.py

Ohne PowerShell und ohne Gedaechtnis: `lauf` und `merken` sind Parameter.
Gemessen wird vor allem, was NICHT passiert - dass keine Art geraten wird,
wo nichts dafuer spricht, und dass ein mehrdeutiger Name nicht aufgeloest
wird, sondern mehrdeutig bleibt.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import probenort
import programme

GESAMT = 0
FEHLER = 0

ROH = [
    {"name": "ARC Raiders", "art": "spiel", "quelle": "steam",
     "pfad": r"D:\SteamLibrary\steamapps\common\ARC Raiders",
     "start": "steam://rungameid/1808500"},
    {"name": "Battlefield™ 6", "art": "spiel", "quelle": "steam",
     "pfad": r"C:\steamapps\common\bf6", "start": "steam://rungameid/2807960"},
    {"name": "Fortnite", "art": "spiel", "quelle": "epic", "pfad": "",
     "start": "com.epicgames.launcher://apps/Fortnite?action=launch"},
    # Aus dem Startmenue, im Ordner "Steam" - daran ist es ein Spiel.
    {"name": "Half-Life", "art": "", "quelle": "startmenue", "ordner": "Steam",
     "pfad": r"C:\Program Files (x86)\Steam\steam.exe", "start": "hl.lnk"},
    # Aus dem Startmenue, ohne Hinweis - dann ist es ein Programm.
    {"name": "Audacity", "art": "", "quelle": "startmenue", "ordner": "Audacity",
     "pfad": r"C:\Program Files\Audacity\audacity.exe", "start": "a.lnk"},
    # Klingt wie ein Spiel, ist keins: der Name entscheidet nicht.
    {"name": "Game Bar Presence Writer", "art": "", "quelle": "startmenue",
     "ordner": "Zubehoer", "pfad": r"C:\Windows\System32\gb.exe", "start": "g.lnk"},
    # Gehoert gar nicht ins Verzeichnis.
    {"name": "Audacity deinstallieren", "art": "", "quelle": "startmenue",
     "ordner": "Audacity", "pfad": "", "start": "u.lnk"},
    {"name": "ARC Raiders", "art": "", "quelle": "desktop",
     "pfad": r"C:\arc.lnk", "start": "arc.lnk"},
]


def pruefe(bedingung, was: str) -> None:
    global GESAMT, FEHLER
    GESAMT += 1
    print("  %s %s" % ("ok  " if bedingung else "FEHL", was))
    if not bedingung:
        FEHLER += 1


def probe_einordnen() -> None:
    print("\nDie Art kommt aus der Herkunft, nicht aus dem Namen")
    e = programme.sehen(lauf=lambda: ROH)
    nach = {x["name"]: x for x in e}
    pruefe(nach["ARC Raiders"]["art"] == "spiel", "Steam-Eintrag ist ein Spiel")
    pruefe(nach["Fortnite"]["art"] == "spiel", "Epic-Eintrag auch")
    pruefe(nach["Half-Life"]["art"] == "spiel",
           "und die Verknuepfung im Steam-Ordner: %s" % nach["Half-Life"]["art"])
    pruefe(nach["Audacity"]["art"] == "programm",
           "Audacity ist ein Programm: %s" % nach["Audacity"]["art"])
    pruefe(nach["Game Bar Presence Writer"]["art"] == "programm",
           "\"Game\" im Namen macht kein Spiel: %s"
           % nach["Game Bar Presence Writer"]["art"])
    pruefe("Audacity deinstallieren" not in nach,
           "die Deinstallation steht nicht drin - sie ist startbar und nie "
           "gemeint")
    pruefe(nach["Battlefield™ 6"]["name"] == "Battlefield™ 6",
           "das ™ bleibt heil: %r" % nach["Battlefield™ 6"]["name"])


def probe_steam_sticht() -> None:
    print("\nSteam weiss es besser als eine Verknuepfung")
    e = programme.sehen(lauf=lambda: ROH)
    arc = [x for x in e if x["name"] == "ARC Raiders"]
    pruefe(len(arc) == 1, "ARC Raiders steht einmal da, nicht zweimal: %d" % len(arc))
    pruefe(arc and arc[0]["start"].startswith("steam://"),
           "und mit dem Steam-Start, nicht mit der Desktop-Verknuepfung: %s"
           % (arc and arc[0]["start"]))


def probe_finden() -> None:
    print("\nNachschlagen, ohne zu raten")
    e = programme.sehen(lauf=lambda: ROH)
    t = programme.finden("arc", e)
    pruefe(t and t[0]["name"] == "ARC Raiders",
           "\"arc\" findet ARC Raiders: %s" % [x["name"] for x in t])
    t = programme.finden("battlefield", e)
    pruefe(t and t[0]["name"].startswith("Battlefield"),
           "\"battlefield\" findet Battlefield: %s" % [x["name"] for x in t])
    t = programme.finden("audacity", e)
    pruefe(t and t[0]["name"] == "Audacity", "und Audacity sich selbst")
    pruefe(programme.finden("gibtsnicht", e) == [],
           "was es nicht gibt, gibt keinen Treffer")
    pruefe(programme.finden("", e) == [], "und nichts gefragt gibt nichts")

    # Mehrdeutig bleibt mehrdeutig: Die Liste kommt vollstaendig zurueck.
    zwei = [{"name": "Doom", "art": "spiel", "start": "a", "pfad": "", "quelle": "steam"},
            {"name": "Doom Eternal", "art": "spiel", "start": "b", "pfad": "", "quelle": "steam"}]
    t = programme.finden("doom", zwei)
    pruefe(len(t) == 2,
           "zwei Doom bleiben zwei - wer hier den ersten nimmt, startet das "
           "falsche Spiel: %s" % [x["name"] for x in t])

    # Nach Art gefiltert.
    t = programme.finden("a", e, art="spiel")
    pruefe(all(x["art"] == "spiel" for x in t),
           "nach Spielen gefragt kommen nur Spiele")


def probe_saetze() -> None:
    print("\nJe Art ein Satz, mit der gezaehlten Zahl")
    e = programme.sehen(lauf=lambda: ROH)
    s = {x["schluessel"]: x["satz"] for x in programme.saetze(e)}
    spiele = sum(1 for x in e if x["art"] == "spiel")
    pruefe("programme:spiel" in s, "ein Satz ueber die Spiele")
    pruefe(str(spiele) in s.get("programme:spiel", ""),
           "mit der gezaehlten Zahl (%d): %s" % (spiele, s.get("programme:spiel")))
    pruefe("programme:werkzeug" not in s,
           "keine leere Ueberschrift fuer eine Art, die niemand vergibt")


def probe_nichts_gefunden() -> None:
    print("\nOhne Fund wird nichts behauptet")
    ort = probenort.ablage("programme")
    try:
        programme.WERKSTATT = ort
        programme.VERZEICHNIS = ort / "programme.json"
        zeilen = []
        b = programme.durchgang(lauf=lambda: [], merken=lambda *a: 1,
                                journal=lambda k, t, **e: zeilen.append((k, t)))
        pruefe(b["gefunden"] == 0 and b["gemerkt"] == 0, "nichts gemerkt")
        pruefe(any(k == "fehler" for k, _ in zeilen),
               "und es steht als Fehler da: %s" % zeilen)
        pruefe(not programme.VERZEICHNIS.exists(),
               "das Verzeichnis wird NICHT leer ueberschrieben - sonst waere "
               "ein misslungener Lauf schlimmer als keiner")
    finally:
        probenort.wegraeumen(ort)


def probe_trockenlauf_und_schreiben() -> None:
    print("\nTrockenlauf schreibt nicht, der echte Lauf schon")
    ort = probenort.ablage("programme")
    try:
        programme.WERKSTATT = ort
        programme.VERZEICHNIS = ort / "programme.json"
        b = programme.durchgang(lauf=lambda: ROH)
        pruefe(b.get("trocken") is True, "als Trockenlauf gemeldet")
        pruefe(not programme.VERZEICHNIS.exists(), "und nichts geschrieben")

        gemerkt = []
        b = programme.durchgang(lauf=lambda: ROH,
                                merken=lambda a, t, q, alt=None: gemerkt.append((a, t)) or 1)
        pruefe(programme.VERZEICHNIS.exists(), "der echte Lauf schreibt es")
        pruefe(len(programme.lesen()) == b["gefunden"],
               "und es liest sich wieder: %d" % len(programme.lesen()))
        pruefe(all(a == "zuhause" for a, _ in gemerkt),
               "die Saetze gehen als `zuhause` ins Gedaechtnis")
        pruefe(programme.finden("arc")[0]["name"] == "ARC Raiders",
               "danach findet `finden` ohne Liste im Argument")
    finally:
        probenort.wegraeumen(ort)


def probe_startet_nichts() -> None:
    print("\nDiese Datei startet nichts")
    quelle = Path(programme.__file__).read_text(encoding="utf-8")
    verboten = [z.strip() for z in quelle.splitlines()
                if ("subprocess.run" in z or "os.startfile" in z
                    or "Popen" in z or "os.system" in z)]
    pruefe(not verboten,
           "kein Aufruf, der etwas ausfuehrt: %s" % verboten)


def main() -> int:
    probe_einordnen()
    probe_steam_sticht()
    probe_finden()
    probe_saetze()
    probe_nichts_gefunden()
    probe_trockenlauf_und_schreiben()
    probe_startet_nichts()
    print("\n%d Proben, %d Fehler" % (GESAMT, FEHLER))
    return 1 if FEHLER else 0


if __name__ == "__main__":
    raise SystemExit(main())
