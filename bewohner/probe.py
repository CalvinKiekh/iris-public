"""Wohin Proben schreiben - und was sie loeschen duerfen.

AM 12.09. GEGEN 21:00 HAT EINE PROBE DIE ECHTE WERKSTATT GELOESCHT.

archiv_test.py raeumte nach jeder Probe `sitzung.WERKSTATT` weg. Die erste
Probe brauchte keine Ablage und bog den Pfad nie um - er zeigte noch auf
werkstatt\\. Weg waren: gedaechtnis.db mit 131 Erinnerungen, ERINNERUNG.md,
journal.jsonl mit der Chronik seit Beginn, erinnerungen.json mit den Terminen,
die Messreihen. werkstatt\\ steht in .gitignore; nichts davon lag in git. Die
Mac-Spiegelung hat ICH.md, WUENSCHE.md, die Werkzeuge und drei JSON-Dateien
zurueckgebracht - der Rest ist endgueltig weg.

Der Riegel dagegen stand danach in archiv_test.py und sitzung_test.py. Das
genuegt nicht: Jede andere Probe kann denselben Fehler wieder machen, und
zwanzig Proben loeschen heute mit `shutil.rmtree(..., ignore_errors=True)`.
Darum steht er jetzt HIER, an der Stelle, die loescht.

DIE REGEL: Geloescht wird nur, was unter einem Probenverzeichnis liegt.

  WURZEL              im Temp-Verzeichnis, fuer alles Neue
  werkstatt\\_*       direkt unter der Werkstatt und mit Unterstrich -
                      so heissen die Probenordner, die es schon gibt

Alles andere wird abgelehnt, nicht "meistens" und nicht "wenn frisch()
aufgerufen wurde". Die Werkstatt selbst kann die Pruefung nicht bestehen: Sie
ist kein Kind von WURZEL, und sie ist nicht `_*`.

Und kein `ignore_errors=True`. Es verschweigt genau den Fall, fuer den es da
waere - dass geloescht wird, was der Probe nicht gehoert.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

HIER = Path(__file__).parent

# Die echte Ablage, beim Import festgehalten. Kein spaeteres Umbiegen eines
# Modulnamens kann daran noch etwas aendern.
ECHTE_WERKSTATT = (HIER / "werkstatt").resolve()

# Wohin Proben gehoeren. Umlegbar ueber IRIS_PROBEN, falls das Temp-
# Verzeichnis einmal nicht taugt - der Riegel gilt dann fuer den neuen Ort.
WURZEL = Path(os.environ.get("IRIS_PROBEN")
              or (Path(tempfile.gettempdir()) / "iris-proben")).resolve()


class Verweigert(SystemExit):
    """Eine Probe wollte loeschen, was ihr nicht gehoert.

    SystemExit und nicht Exception: Ein `except Exception` in einer Probe soll
    das hier nicht auffangen und weiterlaufen.
    """


def _unter(pfad: Path, wurzel: Path) -> bool:
    """Liegt pfad ECHT unterhalb von wurzel? Die Wurzel selbst zaehlt nicht."""
    return wurzel in pfad.parents


def darf_weg(pfad) -> bool:
    """Darf das geloescht werden? Ohne etwas zu tun - zum Pruefen."""
    p = Path(pfad).resolve()
    if p == ECHTE_WERKSTATT or _unter(ECHTE_WERKSTATT, p):
        # Die Werkstatt selbst, oder etwas, das sie enthaelt (ihr Elternteil,
        # das Repo, das Laufwerk). Niemals.
        return False
    if _unter(p, WURZEL):
        return True
    # Die gewachsenen Probenordner: direkt unter der Werkstatt, mit
    # Unterstrich. `werkstatt/_kontext_probe` ja, `werkstatt/gedaechtnis` nein.
    return p.parent == ECHTE_WERKSTATT and p.name.startswith("_")


def ablage(name: str = "probe") -> Path:
    """Ein frischer, leerer Ordner fuer eine Probe - unter WURZEL.

    Wer das nimmt, kann den Fehler vom 12.09. nicht machen: Der Pfad zeigt
    nie auf die Werkstatt, auch wenn die Probe das Umbiegen vergisst.
    """
    WURZEL.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"{name}_", dir=WURZEL))


def wegraeumen(pfad) -> None:
    """Raeumt einen Probenordner weg - und NUR den.

    Eine Probe, die das Umbiegen vergisst, darf hoechstens durchfallen. Sie
    darf nicht loeschen, woran der Bewohner gerade arbeitet.
    """
    p = Path(pfad).resolve()
    if not darf_weg(p):
        raise Verweigert(
            f"ABBRUCH: Diese Probe wollte {p} loeschen. Das liegt nicht unter "
            f"einem Probenverzeichnis ({WURZEL} oder {ECHTE_WERKSTATT}\\_*) - "
            f"es wird nichts geloescht. Hat die Probe ihre Ablage umzubiegen "
            f"vergessen?")
    if not p.exists():
        return
    # Ohne ignore_errors. Bleibt etwas liegen, soll man es sehen.
    shutil.rmtree(p)


def datei_weg(pfad) -> None:
    """Eine einzelne Probendatei. Dieselbe Pruefung, derselbe Grund."""
    p = Path(pfad).resolve()
    if not darf_weg(p):
        raise Verweigert(
            f"ABBRUCH: Diese Probe wollte die Datei {p} loeschen. Sie liegt "
            f"nicht unter einem Probenverzeichnis - es wird nichts geloescht.")
    p.unlink(missing_ok=True)
