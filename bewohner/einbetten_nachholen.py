"""Fehlende Vektoren nachholen - fuer alle Arten, die einen bekommen sollen.

    python -X utf8 einbetten_nachholen.py          Trockenlauf: nur zaehlen
    python -X utf8 einbetten_nachholen.py --echt   rechnet und schreibt

WARUM ES DIE DATEI GIBT: `merken()` bettet nur bestimmte Arten ein, und
`zuhause` und `sitzung` standen nicht in der Liste. Das sind genau die zwei
Arten, die heute dazugekommen sind - B und die Zusammenschau. Beide sind
langlebig und wenige, also der Fall, fuer den der Vektor da ist.

GEMESSEN, und daran war es zu sehen: Auf "Wofuer nutze ich den Rechner?"
lieferte die Suche KEINEN der neun zuhause-Fakten. Sie sagen
"Installationsprogramme", "Modelle", "Bildgenerierung"; die Frage sagt "nutze"
und "Rechner". Ohne gemeinsames Wort findet der Volltext nichts - und 3
Einbettungen auf 216 Erinnerungen heisst, dass die Vektorsuche praktisch aus
war. "Welche Art Spiele habe ich?" traf nur, weil "Spiele" woertlich in dem
einen Satz steht.

Gerechnet wird auf der CPU (num_gpu 0, siehe gedaechtnis.einbetten) - das
drueckt gpt-oss nicht aus dem Grafikspeicher.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER))

import gedaechtnis

# Dieselbe Liste wie in merken(). Steht sie zweimal da, laufen die beiden
# auseinander - darum wird sie hier GELESEN, nicht wiederholt.
ARTEN = ("fakt", "gespraech", "tagesrueckblick", "rueckblick", "zuhause",
         "sitzung")

# So viele auf einmal an bge-m3. Mehr kostet nur Arbeitsspeicher.
STAPEL = 16


def fehlende() -> list[tuple[int, str, str]]:
    """Was einen Vektor haben sollte und keinen hat - nur Gueltiges."""
    db = gedaechtnis.DATENBANK
    if not db.exists():
        raise SystemExit(f"kein Gedaechtnis unter {db}")
    v = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        fragezeichen = ",".join("?" * len(ARTEN))
        return [(int(i), str(a), str(t)) for i, a, t in v.execute(
            f"SELECT e.id, e.art, e.text FROM erinnerung e "
            f"LEFT JOIN einbettung b ON b.id = e.id "
            f"WHERE b.id IS NULL AND e.ersetzt_durch IS NULL "
            f"AND e.art IN ({fragezeichen}) ORDER BY e.id", ARTEN).fetchall()]
    finally:
        v.close()


def nachholen(offen: list[tuple[int, str, str]]) -> int:
    getan = 0
    for ab in range(0, len(offen), STAPEL):
        teil = offen[ab:ab + STAPEL]
        vektoren = gedaechtnis.einbetten([t for _, _, t in teil])
        if not vektoren:
            print(f"  bge-m3 hat nicht geantwortet - {len(offen) - getan} "
                  f"bleiben offen")
            break
        with gedaechtnis._sperre, gedaechtnis._verbindung() as v:
            for (kennung, _, _), vektor in zip(teil, vektoren):
                v.execute("INSERT OR REPLACE INTO einbettung(id, vektor) "
                          "VALUES (?,?)",
                          (kennung, gedaechtnis._packen(vektor)))
        getan += len(teil)
        print(f"  {getan} von {len(offen)}")
    return getan


FRAGEN = ["Wofür nutze ich den Rechner?", "Welche Art Spiele habe ich?",
          "Was liegt auf meinem Desktop?", "Was liegt in meinen Downloads?",
          "Was ist ComfyUI?"]


def suchprobe() -> None:
    print("\n" + "=" * 72)
    print("Suchprobe - wie viele zuhause-Fakten die Suche jetzt findet")
    print("=" * 72)
    for f in FRAGEN:
        treffer = gedaechtnis.abrufen(f, 6)
        zuhause = [t for t in treffer if t["art"] == "zuhause"]
        print(f"\n  {f!r}  -> {len(zuhause)} von {len(treffer)} sind `zuhause`")
        for t in treffer:
            marke = "*" if t["art"] == "zuhause" else " "
            print(f"    {marke} [{t['art']:8}] "
                  f"{' '.join(str(t['text']).split())[:68]}")


def main() -> int:
    offen = fehlende()
    nach_art: dict = {}
    for _, art, _ in offen:
        nach_art[art] = nach_art.get(art, 0) + 1

    with sqlite3.connect(str(gedaechtnis.DATENBANK)) as c:
        da = c.execute("SELECT COUNT(*) FROM einbettung").fetchone()[0]
    print(f"{da} Einbettungen vorhanden, {len(offen)} fehlen:")
    for art, n in sorted(nach_art.items(), key=lambda x: -x[1]):
        print(f"  {art:16} {n}")

    if "--echt" not in sys.argv:
        print("\nTrockenlauf - nichts gerechnet. Mit --echt wirklich.")
        if "--suche" in sys.argv:
            suchprobe()
        return 0

    if offen:
        print()
        nachholen(offen)
    suchprobe()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
