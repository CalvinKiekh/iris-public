"""werkstatt\\gespraech\\ waechst, und niemand raeumt - aber Muell ist es nicht.

    python -X utf8 gespraech_aufraeumen.py              Trockenlauf
    python -X utf8 gespraech_aufraeumen.py --tage 2     andere Frist
    python -X utf8 gespraech_aufraeumen.py --echt       legt wirklich beiseite

WAS DORT LIEGT, und warum es nicht einfach weg kann:

  g-<id>.json     die Frage mit ihrer Antwort. Die App liest den Ordner.
  g-<id>-N.mp3    die gesprochene Antwort. Sie steht im Journal als
                  `audio=gespraech/<id>-N.mp3` - die App kann eine alte
                  Antwort damit NACHSPIELEN.

Darum ist das hier keine Aufraeumfrage, sondern eine Entscheidung ueber
Aufbewahrung: Wie lange soll Calvin eine Antwort nachhoeren koennen? Das ist
seine Entscheidung, nicht meine. Gemessen am 12.09. um 23:40: neun Fragen,
82 Begleitdateien, 9 Megabyte fuer einen Abend.

BEISEITELEGEN, NICHT LOESCHEN - dieselbe Regel wie bei den Erinnerungen. Die
Frage-JSONs wandern nach gespraech\\alt\\ und bleiben lesbar; der Ordner, den
die App und gespraech.py mit `glob("*.json")` durchsehen, wird wieder kurz. Ein
Unterordner faellt aus diesem Muster heraus, das ist nachgesehen.

DIE MP3 BLEIBEN LIEGEN, und das ist keine Faulheit. Nachgesehen in
bridge/resident.py: `audio(rel)` verlangt, dass der Pfad mit "gespraech/"
anfaengt, und prueft `os.path.isfile` DARAUF - literal, ohne zu suchen. Im
Journal steht "gespraech/g-<id>-1.mp3". Verschoebe man sie nach alt\\, zeigte
das Journal ins Leere und keine alte Antwort waere mehr nachhoerbar. Der Ton
bleibt also, wo er ist; wie lange er bleiben soll, ist Calvins Frist.
"""
from __future__ import annotations

from einstellungen import NAME
import json
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
ORDNER = HIER / "werkstatt" / "gespraech"
ALT = ORDNER / "alt"

# Wie lange eine beantwortete Frage im Hauptordner bleibt. Grosszuegig, weil
# die mp3 daran haengt und ein Nachhoeren mehr wert ist als ein kurzer Ordner.
TAGE = 1


def _kandidaten(tage: float, jetzt: float) -> list[tuple[Path, list[Path]]]:
    """(Frage-JSON, ihre Begleitdateien) - nur beantwortete, nur alte.

    Die Begleitdateien werden nur GEZAEHLT, nicht verschoben: Das Journal zeigt
    literal auf gespraech/<id>-N.mp3.
    """
    heraus = []
    grenze = jetzt - tage * 86400
    for p in sorted(ORDNER.glob("g-*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # Offene Fragen NIE anfassen - daran arbeitet er vielleicht gerade.
        if str(d.get("status") or "").lower() != "beantwortet":
            continue
        try:
            wann = float(d.get("antwort_ts") or d.get("ts") or 0)
        except (TypeError, ValueError):
            wann = 0
        if not wann or wann > grenze:
            continue
        kennung = p.stem
        begleiter = [x for x in ORDNER.iterdir()
                     if x.is_file() and x.name.startswith(kennung + "-")]
        heraus.append((p, begleiter))
    return heraus


def durchgang(tage: float = TAGE, echt: bool = False,
              jetzt: float | None = None) -> dict:
    jetzt = time.time() if jetzt is None else jetzt
    kandidaten = _kandidaten(tage, jetzt)
    bytes_ = sum(x.stat().st_size for _, b in kandidaten for x in b)
    bytes_ += sum(p.stat().st_size for p, _ in kandidaten)
    if echt and kandidaten:
        ALT.mkdir(parents=True, exist_ok=True)
        for p, _ in kandidaten:
            try:
                p.replace(ALT / p.name)
            except OSError:
                pass
    return {"fragen": len(kandidaten),
            "begleiter_bleiben": sum(len(b) for _, b in kandidaten),
            "bytes": bytes_, "echt": bool(echt)}


def main() -> int:
    tage = TAGE
    if "--tage" in sys.argv:
        tage = float(sys.argv[sys.argv.index("--tage") + 1])
    echt = "--echt" in sys.argv

    im_ordner = list(ORDNER.glob("g-*.json")) if ORDNER.is_dir() else []
    begleiter = ([x for x in ORDNER.iterdir()
                  if x.is_file() and not x.name.endswith(".json")]
                 if ORDNER.is_dir() else [])
    gesamt = sum(x.stat().st_size for x in ORDNER.iterdir()
                 if x.is_file()) if ORDNER.is_dir() else 0
    print(f"{len(im_ordner)} Fragen, {len(begleiter)} Begleitdateien, "
          f"{gesamt / 1048576:.1f} MB im Hauptordner")

    b = durchgang(tage, echt)
    was = "beiseitegelegt" if echt else "WUERDEN beiseitegelegt"
    print(f"{b['fragen']} Frage-JSONs {was} - beantwortet und aelter als "
          f"{tage:g} Tage")
    print(f"{b['begleiter_bleiben']} Begleitdateien bleiben liegen: Das "
          f"Journal zeigt literal darauf - verschoben waeren alte "
          f"Antworten nicht mehr nachhoerbar.")
    if not echt:
        print("\nTrockenlauf - nichts angefasst. Mit --echt nach "
              "gespraech\\alt\\ verschieben.")
    if b["fragen"] == 0:
        print(f"\nNichts ist alt genug. Die Frist entscheidet, wie lange {NAME} "
              "eine Antwort\nnachhoeren kann - das ist seine Entscheidung, "
              "nicht meine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
