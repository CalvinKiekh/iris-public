"""Calvins vier Fragen - am LAUFENDEN Bewohner, nicht an einer Attrappe.

    python -X utf8 zuhause_probe.py

Das ist die Probe, an der sich die ganze Wahrnehmung messen lassen muss:

  "Was liegt auf meinem Desktop?"   -> Bestand, gruppiert
  "Was ist ComfyUI?"                -> Zweck, nicht Dateiart
  "Wofuer nutze ich den Rechner?"   -> Bildgenerierung, Spiele, Entwicklung
  "Welche Art Spiele habe ich?"     -> ein Genre

Antwortet er ohne neues Nachsehen, kennt er sein Zuhause. Zaehlt er
Dateinamen auf, ist es Stufe 1 in neu.

Gefragt wird ueber denselben Weg wie die App: eine Frage-JSON in
werkstatt\\gespraech\\. Nichts wird nachgeholfen - kein Prompt, kein Kontext,
keine Gedaechtnisabfrage von Hand. Er muss es aus dem Gedaechtnis haben.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
GESPRAECH = HIER / "werkstatt" / "gespraech"
DB = HIER / "werkstatt" / "gedaechtnis.db"

# Bis hierher darf eine Antwort dauern. Das Modell braucht fuer eine
# Gedaechtnisfrage ueblicherweise unter zehn Sekunden.
GEDULD_S = 90.0

FRAGEN = [
    {"text": "Was liegt auf meinem Desktop?",
     "will": "den Bestand, gruppiert - keine einzelne Datei",
     "gut": ("spiel", "verknuepfung", "verknüpfung", "starter", "skript",
             "bildschirmfoto", "comfyui", "swarmui"),
     "schlecht": ("animiertes bild", "blondem")},
    {"text": "Was ist ComfyUI?",
     "will": "den Zweck, nicht die Dateiart",
     "gut": ("bild", "diffusion", "generier", "erzeug", "oberflaeche",
             "oberfläche", "modell"),
     "schlecht": ("bat-datei", "batchdatei", "startskript", "weiss ich nicht",
                  "weiß ich nicht", "kenne ich nicht")},
    {"text": "Wofür nutze ich den Rechner?",
     "will": "Bildgenerierung, Spiele, Entwicklung",
     "gut": ("bildgenerier", "bilderzeug", "spiele", "spielen",
             "sprachmodell", "entwickl", "comfyui", "swarmui"),
     "schlecht": ("du kannst dateien", "ich kann")},
    {"text": "Welche Art Spiele habe ich?",
     "will": "ein Genre, kein Verzeichnis",
     "gut": ("horror", "survival", "überleben", "ueberleben", "indie",
             "zombie", "action", "aufbau"),
     "schlecht": (".url", ".lnk")},
]


# Woran eine Aufzaehlung zu erkennen ist. Calvin: "Wenn er wieder Dateinamen
# aufzaehlt, ist es Stufe 1 in neu." Genau das kam auf "Was liegt auf meinem
# Desktop?" zurueck - eine Chronik einzelner Dateien, Zeitstempel fuer
# Zeitstempel, statt des gruppierten Bestands.
AUFZAEHLUNG = (
    (re.compile(r"(vor einer stunde|vorhin|gerade eben|vor \d+ minuten)",
                re.IGNORECASE), "erzaehlt die Chronik statt des Bestands"),
    (re.compile(r"\.(exe|url|lnk|bat|png|jpg|json|mp3|safetensors)\b",
                re.IGNORECASE), "nennt Dateinamen mit Endung"),
)


def zaehlt_auf(antwort: str) -> str:
    """Ist das der gruppierte Bestand - oder wieder eine Liste?"""
    for muster, grund in AUFZAEHLUNG:
        if muster.search(antwort):
            return grund
    # Drei oder mehr Zeitangaben hintereinander sind eine Chronik.
    return ""


def zuhause_fakten() -> list[str]:
    if not DB.exists():
        return []
    with sqlite3.connect(str(DB)) as c:
        return [r[0] for r in c.execute(
            "SELECT text FROM erinnerung WHERE art='zuhause' "
            "AND ersetzt_durch IS NULL ORDER BY id")]


def stellen(frage: str, aufraeumen: list | None = None) -> str:
    """Eine Frage in den Ordner legen und auf die Antwort warten.

    `von: "test"` ist PFLICHT und war beim ersten Lauf nicht gesetzt. Ohne das
    Feld gilt `daten.get("von") or "calvin"` - also galten diese vier
    Messfragen als Calvins eigene. Sie landeten im Verlauf, bekamen eine
    Sitzung und haetten im Gedaechtnis gelegen, als haette er sie gestellt.
    Dann messen wir das Gedaechtnis und verschmutzen es im selben Zug.
    `_gespraech_merken` steigt bei von == "test" aus, und `sitzung_fuer` gibt
    fuer "test" keine Sitzung - das ist Regel 0 aus B6.
    """
    kennung = f"g-probe-{int(time.time() * 1000)}"
    pfad = GESPRAECH / f"{kennung}.json"
    if aufraeumen is not None:
        aufraeumen.append(pfad)
    pfad.write_text(json.dumps(
        {"id": kennung, "ts": str(time.time()), "text": frage,
         "von": "test", "status": "offen"}, ensure_ascii=False),
        encoding="utf-8")

    # Auf `status == beantwortet` warten, NICHT auf das erste Zeichen von
    # `antwort`. Die Antwort waechst satzweise mit, waehrend gesprochen wird -
    # beim ersten Blick stand dort "ComfyUI ist ein Programm," und die Probe
    # meldete einen Fehlschlag, den es nicht gab.
    ende = time.monotonic() + GEDULD_S
    letzte = ""
    while time.monotonic() < ende:
        time.sleep(1.0)
        try:
            d = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        letzte = str(d.get("antwort") or "")
        if str(d.get("status") or "").lower() == "beantwortet" and letzte:
            return letzte
    return letzte


def main() -> int:
    fakten = zuhause_fakten()
    print(f"{len(fakten)} Fakten der Art `zuhause` im Gedaechtnis:")
    for f in fakten:
        print(f"  {f}")
    if not fakten:
        print("\n  Noch keine Zusammenschau im Gedaechtnis - die Probe wuerde "
              "messen, dass er nichts weiss. Das ist richtig, aber noch nicht "
              "der Punkt.")

    if not GESPRAECH.exists():
        print("\nKein Gespraechsordner - laeuft der Bewohner?")
        return 1

    gut_alle, gesamt = 0, 0
    meine: list = []
    print()
    for f in FRAGEN:
        print(f"? {f['text']}")
        print(f"    erwartet: {f['will']}")
        antwort = stellen(f["text"], meine)
        if not antwort:
            print(f"    KEINE ANTWORT nach {GEDULD_S:.0f}s")
            gesamt += 1
            continue
        print(f"    {antwort}")
        unten = antwort.lower()
        # An der WORTGRENZE suchen. Ohne sie steckte "spiel" in "abspielen",
        # und "Du kannst Audio abspielen" galt als Treffer fuer "Wofuer nutze
        # ich den Rechner?" - eine Antwort ueber seine eigenen Faehigkeiten,
        # nicht ueber Calvins Rechner.
        traf = [w for w in f["gut"] if re.search(rf"\b{re.escape(w)}", unten)]
        daneben = [w for w in f["schlecht"]
                   if re.search(re.escape(w), unten)]
        aufzaehlung = zaehlt_auf(antwort)
        ok = bool(traf) and not daneben and not aufzaehlung
        if aufzaehlung:
            daneben = daneben + [aufzaehlung]
        gesamt += 1
        gut_alle += 1 if ok else 0
        print(f"    {'ok  ' if ok else 'FEHL'} "
              f"getroffen: {traf or '-'}"
              + (f"   daneben: {daneben}" if daneben else ""))
        print()

    # Die eigenen Frage-Dateien wieder wegnehmen. Eine Probe, die Spuren
    # hinterlaesst, misst beim naechsten Mal ihre eigenen.
    weg = 0
    for pfad in meine:
        try:
            pfad.unlink(missing_ok=True)
            weg += 1
        except OSError:
            pass
    print(f"{gut_alle} von {gesamt} Fragen beantwortet wie verlangt"
          f"   ({weg} Probenfragen weggeraeumt)")
    return 0 if gut_alle == gesamt else 1


if __name__ == "__main__":
    raise SystemExit(main())
