"""Die 163 Einzeldateien im Gedaechtnis ueberholen - wie F.1, nicht loeschen.

    python -X utf8 datei_ueberholen.py              Trockenlauf: nur zaehlen
    python -X utf8 datei_ueberholen.py --suche      dazu die Suchprobe
    python -X utf8 datei_ueberholen.py --echt       schreibt
    python -X utf8 datei_ueberholen.py --rueckweg   stellt alles wieder her

DERSELBE FEHLER WIE HEUTE MITTAG, nur mit anderem Inhalt. F.1 hat 43 rohe
Gespraechsprotokolle ueberholt, weil sie bei der Suche das verdraengten, was
bleiben soll. Jetzt liegen 163 Saetze der Art `datei` dort:

    "Eine Datei namens WhatsApp Installer.exe, 1264 Kilobyte, Art unbekannt."
    "Eine Tonaufnahme namens Yeah.mp3, 150 Sekunden, 48000 Hertz."

Gemessen: 163 `datei` gegen 10 `zuhause`, 6 `ereignis`, 3 `fakt`. Das
Verhaeltnis IST die Diagnose. Auf "Was ist ComfyUI?" kam an erster Stelle
"Eine Datei namens ComfyUI starten.bat, 0 Kilobyte, Art unbekannt" zurueck -
weil "ComfyUI" woertlich darin steht und der Volltext nichts anderes kennt.

Eine einzelne Datei ist MATERIAL, kein Wissen. Sie entsteht seit 9b3ee01 nicht
mehr im Gedaechtnis; diese 163 lagen schon da.

ZUERST UMZIEHEN, DANN UEBERHOLEN - sonst ist es nicht verlustfrei.
bestand.py liest diese Saetze, um ein Bildschirmfoto von einem Foto zu
unterscheiden; am Dateinamen ist das nicht zu sehen. Sie wandern darum nach
werkstatt\\beschreibungen.json, wo das Material hingehoert. Erst danach faellt
die Marke.

UEBERHOLEN, NICHT LOESCHEN. `ersetzt_durch = 0` heisst "veraltet, ohne
Nachfolger": Die Zeile bleibt lesbar, faellt aber aus jeder Suche heraus, weil
abrufen() auf `ersetzt_durch IS NULL` filtert. Dieselbe Marke und dieselbe
Begruendung wie in f1_ueberholen.py - eine 0 kann nie eine echte Kennung sein,
weil SQLite bei 1 anfaengt, also reisst keine Kette.

VORSICHTIG AN DREI STELLEN:
  - Nur Zeilen mit einer Quelle. Eine `datei`-Zeile ohne Quelle ist nicht vom
    Wahrnehmungsfaden angelegt worden - die wird gemeldet, nicht angefasst.
  - Nur Zeilen mit `ersetzt_durch IS NULL`.
  - Der Trockenlauf ist die Voreinstellung. Schreiben muss man verlangen.
"""
from __future__ import annotations

from einstellungen import NAMENS
import json
import sqlite3
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

DB = HIER / "werkstatt" / "gedaechtnis.db"
ART = "datei"
VERALTET = 0


def lesen() -> tuple[list[dict], list[dict], list[dict]]:
    """(mit Quelle, ohne Quelle, schon ueberholt) - nur lesen."""
    if not DB.exists():
        raise SystemExit(f"kein Gedaechtnis unter {DB}")
    v = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        zeilen = v.execute(
            "SELECT id, ts, text, quelle, ersetzt_durch FROM erinnerung "
            "WHERE art=? ORDER BY id", (ART,)).fetchall()
    finally:
        v.close()

    mit, ohne, schon = [], [], []
    for kennung, ts, text, quelle, ersetzt in zeilen:
        e = {"id": int(kennung), "ts": float(ts or 0), "text": str(text or ""),
             "quelle": str(quelle or ""), "ersetzt_durch": ersetzt}
        if ersetzt is not None:
            schon.append(e)
        elif e["quelle"]:
            mit.append(e)
        else:
            ohne.append(e)
    return mit, ohne, schon


def umziehen(mit: list[dict]) -> tuple[int, int]:
    """Die Saetze nach beschreibungen.json bringen. (neu, schon da)"""
    import wahrnehmung

    vorhanden = wahrnehmung.beschreibungen()
    neu = 0
    for e in mit:
        if vorhanden.get(e["quelle"]) == e["text"]:
            continue
        vorhanden[e["quelle"]] = e["text"]
        neu += 1
    if neu:
        wahrnehmung.WERKSTATT.mkdir(parents=True, exist_ok=True)
        t = wahrnehmung.BESCHREIBUNGEN.with_suffix(".json.tmp")
        t.write_text(json.dumps(vorhanden, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        t.replace(wahrnehmung.BESCHREIBUNGEN)
    return neu, len(mit) - neu


def schreiben(mit: list[dict]) -> int:
    if not mit:
        return 0
    import gedaechtnis
    gedaechtnis.anlegen()
    kennungen = [e["id"] for e in mit]
    fragezeichen = ",".join("?" * len(kennungen))
    with gedaechtnis._sperre, gedaechtnis._verbindung() as v:
        # Die Einbettung bleibt stehen - abrufen() filtert ueber die
        # Haupttabelle, und beim Rueckweg waere sie sonst verloren.
        z = v.execute(
            f"UPDATE erinnerung SET ersetzt_durch=? WHERE id IN "
            f"({fragezeichen}) AND art=? AND ersetzt_durch IS NULL",
            [VERALTET] + kennungen + [ART])
        return z.rowcount


def rueckweg() -> int:
    import gedaechtnis
    gedaechtnis.anlegen()
    with gedaechtnis._sperre, gedaechtnis._verbindung() as v:
        z = v.execute("UPDATE erinnerung SET ersetzt_durch=NULL "
                      "WHERE art=? AND ersetzt_durch=?", (ART, VERALTET))
        return z.rowcount


def _uhr(ts: float) -> str:
    return time.strftime("%d.%m %H:%M", time.localtime(ts)) if ts else "?"


def bestand_danach() -> None:
    """Was nach dem Ueberholen noch in der Suche liegt."""
    v = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        zeilen = v.execute(
            "SELECT art, COUNT(*) FROM erinnerung WHERE ersetzt_durch IS NULL "
            "GROUP BY art ORDER BY -COUNT(*)").fetchall()
    finally:
        v.close()
    print("\nWas die Suche danach sieht:")
    for art, n in zeilen:
        print(f"  {art:16} {n}")


FRAGEN = ["Welche Art Spiele habe ich?", "Was liegt auf meinem Desktop?",
          "Wofür nutze ich den Rechner?", "Was ist ComfyUI?",
          "Was liegt in meinen Downloads?"]


def suchprobe() -> None:
    import gedaechtnis
    print("\n" + "=" * 72)
    print(f"Suchprobe - was die Suche JETZT auf {NAMENS} Fragen liefert")
    print("=" * 72)
    for f in FRAGEN:
        print(f"\n  {f!r}")
        treffer = gedaechtnis.abrufen(f, 5)
        if not treffer:
            print("      (nichts)")
        for t in treffer:
            print(f"      [{t['art']:8}] "
                  f"{' '.join(str(t['text']).split())[:72]}")


def main() -> int:
    if "--rueckweg" in sys.argv:
        print(f"{rueckweg()} Dateizeilen wieder gueltig.")
        return 0

    mit, ohne, schon = lesen()
    gesamt = len(mit) + len(ohne) + len(schon)
    print("=" * 72)
    print(f"Trockenlauf - {gesamt} Erinnerungen der Art {ART!r}")
    print("=" * 72)
    print(f"  ueberholen       {len(mit):4}  (mit Quelle, vom "
          f"Wahrnehmungsfaden)")
    print(f"  ohne Quelle      {len(ohne):4}  (werden NICHT angefasst)")
    print(f"  schon ueberholt  {len(schon):4}  (werden NICHT angefasst)")

    print("\nEine Auswahl dessen, was ueberholt wuerde:")
    for e in mit[:8]:
        print(f"  [{e['id']:4}] {_uhr(e['ts'])}  {e['text'][:64]}")
    if len(mit) > 8:
        print(f"  ... und {len(mit) - 8} weitere")
    if ohne:
        print("\nOhne Quelle, nicht angefasst:")
        for e in ohne:
            print(f"  [{e['id']:4}] {e['text'][:64]}")

    if "--suche" in sys.argv:
        suchprobe()

    if "--echt" not in sys.argv:
        print("\nTrockenlauf - nichts geschrieben. Mit --echt wirklich.")
        return 0

    neu, schon_da = umziehen(mit)
    print(f"\nNach beschreibungen.json umgezogen: {neu} neu, "
          f"{schon_da} lagen schon dort.")
    n = schreiben(mit)
    print(f"{n} Dateizeilen ueberholt (ersetzt_durch={VERALTET}).")
    bestand_danach()
    print("\nRueckweg:  python -X utf8 datei_ueberholen.py --rueckweg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
