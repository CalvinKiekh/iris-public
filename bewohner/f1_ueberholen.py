"""F.1 - die Zustandsprotokolle ueberholen, nicht loeschen.

    python -X utf8 f1_ueberholen.py              Trockenlauf: nur zaehlen
    python -X utf8 f1_ueberholen.py --suche      dazu die Suchprobe (F.3)
    python -X utf8 f1_ueberholen.py --echt       schreibt (fragt vorher nach)
    python -X utf8 f1_ueberholen.py --rueckweg   stellt alles wieder her

Im Gedaechtnis liegen rohe Mitschriften der Art `gespraech`:

    "Calvin fragte: Was kannst du? Ich antwortete: Ich sehe den Bildschirm ..."

Achtmal dieselbe Chronikfrage, fuenfmal dieselbe Faehigkeitsfrage, dazu
Messwerte, die eine Sekunde lang stimmten. Sie sind nicht falsch, aber sie
verdraengen bei der Suche das, was bleiben soll - `wissen.lohnt()` weist sie
seit e9defc4 ab, nur lagen sie schon da.

UEBERHOLEN, NICHT LOESCHEN. `ersetzt_durch = 0` heisst "veraltet, ohne
Nachfolger": Die Zeile bleibt lesbar, faellt aber aus jeder Suche heraus, weil
`abrufen()` auf `ersetzt_durch IS NULL` filtert (gedaechtnis.py:552 und :566,
nachgesehen). Das ist Calvins Regel von heute frueh - korrigieren statt
loeschen - und es macht jeden Schritt umkehrbar.

WARUM 0 SICHER IST, und das ist nachgesehen, nicht angenommen: `vergessen()`
loescht die ganze Kette mit, `DELETE FROM erinnerung WHERE ersetzt_durch IN
(<die vergessenen Kennungen>)` (gedaechtnis.py:515). Eine 0 kann dort nie
auftauchen, weil SQLite-Kennungen bei 1 anfangen. Die Marke zeigt also
bewusst auf eine Erinnerung, die es nicht gibt, und keine Kette reisst.

VORSICHTIG AN DREI STELLEN:
  - Nur Zeilen, die sich sauber lesen lassen. Wer sich nicht in Frage und
    Antwort trennen laesst, wird NICHT angefasst, sondern gemeldet.
  - Nur Zeilen mit `ersetzt_durch IS NULL`. Eine schon ueberholte Zeile wird
    nicht ueberschrieben - sonst ginge ihr Nachfolger verloren.
  - Der Trockenlauf ist die Voreinstellung. Schreiben muss man verlangen.
"""
from __future__ import annotations

from einstellungen import NAME
import sqlite3
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

import wissen

DB = HIER / "werkstatt" / "gedaechtnis.db"
ART = "gespraech"
# Die Marke. Nicht NULL (dann waere die Zeile wieder gueltig) und keine echte
# Kennung (es gibt keinen Nachfolger).
VERALTET = 0

# So hat gespraech.py die Zeile geschrieben (gespraech.py:661):
#   f"Calvin fragte: {frage} Ich antwortete: {antwort}"[:500]
VORNE = f"{NAME} fragte:"
MITTE = "Ich antwortete:"


def lesen() -> tuple[list[dict], list[dict]]:
    """Die Protokolle, getrennt in lesbar und unlesbar. Nur lesen."""
    if not DB.exists():
        raise SystemExit("kein Gedaechtnis unter %s" % DB)
    # Schreibgeschuetzt: Solange eine Messung laeuft, wird hier nichts
    # angefasst und nichts gesperrt.
    v = sqlite3.connect("file:%s?mode=ro" % DB.as_posix(), uri=True)
    try:
        zeilen = v.execute(
            "SELECT id, ts, text, ersetzt_durch FROM erinnerung "
            "WHERE art=? ORDER BY id", (ART,)).fetchall()
    finally:
        v.close()

    lesbar, unlesbar = [], []
    for kennung, ts, text, ersetzt in zeilen:
        t = str(text)
        eintrag = {"id": int(kennung), "ts": float(ts or 0), "text": t,
                   "ersetzt_durch": ersetzt}
        ohne_vorne = t.split(VORNE, 1)[-1] if VORNE in t else t
        if MITTE not in ohne_vorne:
            # Kein Trennwort: abgeschnitten, von Hand angelegt oder aus einer
            # aelteren Fassung. Nicht anfassen.
            unlesbar.append(eintrag)
            continue
        frage, antwort = ohne_vorne.split(MITTE, 1)
        eintrag["frage"] = frage.strip()
        eintrag["antwort"] = antwort.strip()
        lesbar.append(eintrag)
    return lesbar, unlesbar


def auswaehlen(lesbar: list[dict]) -> tuple[list[dict], list[dict]]:
    """Was ueberholt wird, und was bleibt. Reine Messung ueber wissen.lohnt()."""
    weg, bleibt = [], []
    for e in lesbar:
        if e["ersetzt_durch"] is not None:
            continue                      # schon ueberholt, nicht anfassen
        (bleibt if wissen.lohnt(e) else weg).append(e)
    return weg, bleibt


def _uhr(ts: float) -> str:
    return time.strftime("%d.%m %H:%M", time.localtime(ts)) if ts else "?"


def zeigen(weg: list[dict], bleibt: list[dict],
           unlesbar: list[dict], schon: list[dict]) -> None:
    gesamt = len(weg) + len(bleibt) + len(unlesbar) + len(schon)
    print("=" * 72)
    print("F.1 Trockenlauf - %d Protokolle der Art %r" % (gesamt, ART))
    print("=" * 72)
    print("  ueberholen      %3d" % len(weg))
    print("  bleiben         %3d" % len(bleibt))
    print("  schon ueberholt %3d  (werden nicht angefasst)" % len(schon))
    print("  unlesbar        %3d  (werden nicht angefasst)" % len(unlesbar))

    print("\nWas ueberholt wuerde:")
    for e in weg:
        print("  [%3d] %s  %s" % (e["id"], _uhr(e["ts"]), e["frage"][:62]))

    print("\nWas BLEIBT - und das ist die Stelle, die zaehlt:")
    for e in bleibt:
        print("  [%3d] %s  %s" % (e["id"], _uhr(e["ts"]), e["frage"][:62]))

    if unlesbar:
        print("\nUnlesbar, nicht angefasst:")
        for e in unlesbar:
            print("  [%3d] %s" % (e["id"], e["text"][:66]))
    if schon:
        print("\nSchon ueberholt, nicht angefasst:")
        for e in schon:
            print("  [%3d] -> %s" % (e["id"], e["ersetzt_durch"]))


# Die Suchprobe aus F.3: dieselben Begriffe vor und nach dem Ueberholen.
# Ohne sie wuesste niemand, ob es geholfen hat - "die Suche liefert Muell"
# war gemessen, also muss auch das Gegenteil gemessen werden.
BEGRIFFE = ["Wie heißt meine Tochter?", "Was weißt du über Lena?",
            "Wer ist Sara?", f"Woran arbeitet {NAME}?",
            "Was ist letzte Nacht passiert?"]


def suchprobe() -> None:
    import gedaechtnis
    print("\n" + "=" * 72)
    print("Suchprobe (F.3) - was die Suche JETZT auf diese Fragen liefert")
    print("=" * 72)
    for b in BEGRIFFE:
        treffer = gedaechtnis.abrufen(b, 5)
        print("\n  %r" % b)
        if not treffer:
            print("      (nichts)")
        for t in treffer:
            print("      [%s] %s" % (t["art"], " ".join(
                str(t["text"]).split())[:78]))


def schreiben(weg: list[dict]) -> int:
    """Setzt die Marke. Ueber gedaechtnis, damit die Sperre gilt."""
    if not weg:
        return 0
    import gedaechtnis
    gedaechtnis.anlegen()
    kennungen = [e["id"] for e in weg]
    fragezeichen = ",".join("?" * len(kennungen))
    with gedaechtnis._sperre, gedaechtnis._verbindung() as v:
        # Die Einbettung bleibt stehen: abrufen() filtert ueber die
        # Haupttabelle, und beim Rueckweg waere sie sonst verloren.
        z = v.execute(
            "UPDATE erinnerung SET ersetzt_durch=? "
            "WHERE id IN (%s) AND art=? AND ersetzt_durch IS NULL"
            % fragezeichen, [VERALTET] + kennungen + [ART])
        return z.rowcount


def rueckweg() -> int:
    import gedaechtnis
    gedaechtnis.anlegen()
    with gedaechtnis._sperre, gedaechtnis._verbindung() as v:
        z = v.execute("UPDATE erinnerung SET ersetzt_durch=NULL "
                      "WHERE art=? AND ersetzt_durch=?", (ART, VERALTET))
        return z.rowcount


def main() -> int:
    if "--rueckweg" in sys.argv:
        n = rueckweg()
        print("%d Protokolle wieder gueltig." % n)
        return 0

    lesbar, unlesbar = lesen()
    schon = [e for e in lesbar if e["ersetzt_durch"] is not None]
    weg, bleibt = auswaehlen(lesbar)
    zeigen(weg, bleibt, unlesbar, schon)

    if "--suche" in sys.argv:
        suchprobe()

    if "--echt" not in sys.argv:
        print("\nTrockenlauf - nichts geschrieben.")
        print("Zum Ausfuehren: --echt   |   Rueckweg danach: --rueckweg")
        return 0

    print("\n%d Zeilen werden auf ersetzt_durch=%d gesetzt."
          % (len(weg), VERALTET))
    n = schreiben(weg)
    print("%d Zeilen ueberholt. Rueckweg: python f1_ueberholen.py --rueckweg"
          % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
