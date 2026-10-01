"""Sets up the workshop of a new resident: his tools and what is built into him.

    python -X utf8 einrichten.py              add what is missing
    python -X utf8 einrichten.py --ersetzen   also replace the tools that are there

Two lists tell him what he can do, and he reads both (kann.py):
werkstatt/werkzeuge.json, the tools he calls, and werkstatt/faehigkeiten.json,
what runs inside him. The first resident's lists stay out of the repo - they
record his own history, dates and names included - so a new one starts
without either and would not know what he has.

He loads his tools from werkstatt/werkzeuge/ and uses only those entered in
werkstatt/werkzeuge.json. The repo keeps them in bewohner/werkzeuge/ -
spiegeln.sh brings them from the PC - so a fresh workshop starts without
any, and some of his own code imports them (erinnern, sehen, ansprechen).

Every tool goes through his own acceptance, werkzeuge.pruefen: read the
source for what is forbidden, then run its --selbsttest. Only what passes
is entered. A tool that fails here is reported and left out; platzverlauf,
for instance, measures drive C: and passes only on Windows.

faehigkeiten.json is written from FAEHIGKEITEN below: name and purpose,
no result, and none of them marked as tried - a new resident has not used
any of them yet, and says so when asked. An existing one is never touched,
not even with --ersetzen: it is where he records what came of each.

This is the one script that creates the workshop on purpose: it is setup.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))
import werkzeuge  # noqa: E402
from einstellungen import NAME, NAMENS  # noqa: E402

QUELLE = HIER / "werkzeuge"

# What each tool is for - as the first resident entered it. The entry is his
# own words; werkzeuge.json itself stays out of the repo with the rest of him.
ZWECKE = {
    "platzverlauf": "Hält den freien Platz auf C fest und nennt den Trend",
    "sehen": "Sieht den Bildschirm an und beschreibt in einem Satz, was darauf zu sehen ist",
    "stimme_hoeren": "Misst Tonhoehe, Klangfarbe, Pausen und Dynamik einer Aufnahme",
    "lesen": "Liest einen Text und beantwortet daraus, auch aus langen Dateien",
    "rhythmus": "Erkennt Muster im Tageslauf und meldet Abweichungen vom Üblichen",
    "erinnern": "Haelt Termine fest und meldet sie zur rechten Zeit",
    "ansprechen": "Entscheidet, ob er jetzt von sich aus sprechen darf",
    "netz": "Sagt in Namen, wer im Heimnetz ist und seit wann",
    "auftrag": "Prueft, ob ein Auftrag an Claude fuer sich steht, und schlaegt die Nachpruefung vor",
    "wuensche": "Ordnet ein, was wirklich fehlt, und ob es einen Antrag braucht",
}


# What is built into him, in his words. {NAME} and {NAMENS} become the name
# from the configuration. "Den Dienst neu starten" is a right, not a wish:
# eingreifen.py grants it in code, so every resident has it from the start.
FAEHIGKEITEN = (
    ("Anträge stellen",
     "Frage {NAME} um Erlaubnis, wenn etwas außerhalb meiner Werkstatt liegt, statt es einfach zu tun"),
    ("Gedächtnis",
     "Behalte, was {NAME} mir sagt, und finde es wieder, auch wenn später mit anderen Worten danach gefragt wird"),
    ("Warteschlange mit Vorrang",
     "Lasse {NAME} vor. Was {NAME} fragt, kommt vor allem anderen dran, auch wenn ich gerade an etwas anderem sitze"),
    ("Vergessen",
     "Nehme etwas wieder aus meinem Gedächtnis heraus, wenn {NAME} es sagt, samt allem, was denselben Satz weiterträgt"),
    ("Sprechen",
     "Spreche meine Antworten mit einer Stimme, statt sie nur hinzuschreiben"),
    ("Nachtrag",
     "Schiebt {NAME} mitten in meiner Antwort noch etwas nach, antworte ich auf beides zusammen und wiederhole das schon Gesagte nicht"),
    ("Selbstwahrnehmung",
     "Messe, wie es mir selbst geht: wie schnell ich denke, wie voll die Grafikkarte ist, ob Reste von mir ohne Elternprozess weiterlaufen"),
    ("Entwurf schützen",
     "Was {NAME} noch tippt und nicht abgeschickt hat, beantworte ich nicht"),
    ("Vordenken",
     "Denke schon nach, während {NAME} noch tippt, damit die Antwort da ist, sobald die Nachricht abgeschickt ist"),
    ("Lagebild",
     "Weiß ohne Nachdenken, wie spät es ist, welche Tageszeit, wie lange ich schon arbeite, wie viel Platz frei ist und wer im Heimnetz ist"),
    ("Neues von selbst bemerken",
     "Sehe von selbst, wenn in meiner Werkstatt etwas Neues liegt, und sage in einem Satz, was es ist - Text, Bild, PDF oder Ton"),
    ("Werkzeuge bauen lassen",
     "Fehlt mir etwas, lasse ich mir ein Werkzeug bauen und nehme es selbst ab - erst wenn sein Selbsttest durchläuft, gehört es mir"),
    ("Aufschreiben, wer ich bin",
     "Schreibe selbst auf, wer ich bin und was mir fehlt, aus dem, was ich erlebt habe"),
    ("Erinnerungen",
     "Melde einen Termin, wenn er dran ist, von selbst und ohne dass {NAME} noch einmal fragt"),
    ("Von sich aus sprechen",
     "Spreche {NAME} von mir aus an, wenn etwas es wert ist, und schweige nachts und während der Arbeit"),
    ("Den Dienst neu starten",
     "Darf den Dienst, mit dem ich denke, neu starten, wenn er nicht mehr antwortet"),
    ("Nächtlicher Rückblick",
     "Mache aus einer Nacht Protokoll ein paar Sätze, die bleiben: was ich gebaut habe, was schiefging, was ich daraus gelernt habe"),
)


def faehigkeiten_anlegen() -> None:
    ziel = werkzeuge.WERKSTATT / "faehigkeiten.json"
    if ziel.exists():
        print("  ok   faehigkeiten.json liegt schon da - unveraendert")
        return
    jetzt = time.time()
    liste = [{"name": name,
              "zweck": zweck.format(NAME=NAME, NAMENS=NAMENS),
              "ergebnis": "",
              "geprueft": False,
              "erstellt": jetzt,
              "aufruf": None}
             for name, zweck in FAEHIGKEITEN]
    tmp = ziel.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(liste, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ziel)
    print(f"  ok   faehigkeiten.json mit {len(liste)} Eintraegen angelegt")


def main() -> int:
    ersetzen = "--ersetzen" in sys.argv
    werkzeuge.ORDNER.mkdir(parents=True, exist_ok=True)
    faehigkeiten_anlegen()
    verzeichnis = werkzeuge.verzeichnis_lesen()
    fehlgeschlagen = []
    for datei in sorted(QUELLE.glob("*.py")):
        name = datei.stem
        ziel = werkzeuge.ORDNER / datei.name
        if ziel.exists() and not ersetzen:
            stand = "liegt schon da"
        else:
            shutil.copy2(datei, ziel)
            stand = "kopiert"
        if name in verzeichnis and not ersetzen:
            print(f"  ok   {name:14} {stand}, schon eingetragen")
            continue
        ok, ergebnis = werkzeuge.pruefen(name)
        if ok:
            werkzeuge.eintragen(name, ZWECKE.get(name, name), ergebnis)
            print(f"  ok   {name:14} {stand}, abgenommen und eingetragen")
        else:
            fehlgeschlagen.append(name)
            print(f"  --   {name:14} {stand}, nicht abgenommen: {ergebnis}")
    ohne_zweck = sorted({p.stem for p in QUELLE.glob("*.py")} - set(ZWECKE))
    if ohne_zweck:
        print(f"\nOhne Zweck in ZWECKE, eingetragen unter ihrem Namen: {', '.join(ohne_zweck)}")
    print(f"\nWerkstatt: {werkzeuge.WERKSTATT}")
    if fehlgeschlagen:
        print(f"Nicht eingetragen: {', '.join(fehlgeschlagen)} - er benutzt sie erst, "
              f"wenn sie hier bestehen.")
    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    raise SystemExit(main())
