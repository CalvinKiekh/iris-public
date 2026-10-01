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

Der Name ist mit Bedacht nicht `probe` - ein halbes Dutzend Proben hat eine
oertliche Variable dieses Namens, und ein `import probe` daneben wuerde sie
verdecken, ohne einen Fehler zu werfen.

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

from einstellungen import NAME
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


def eine_probe_laeuft() -> bool:
    """Laeuft gerade eine Probe - nicht der Bewohner?

    Am Namen des gestarteten Programms, nicht an einem Schalter, den eine
    Probe zu setzen vergessen kann. Genau dieses Vergessen ist der Fehler,
    gegen den der ganze Riegel steht.
    """
    import sys
    erstes = Path(sys.argv[0]).name.lower() if sys.argv else ""
    return erstes.endswith("_test.py") or erstes.startswith("beweis_")


def darf_schreiben(pfad) -> bool:
    """Darf dahin geschrieben werden? Ohne etwas zu tun - zum Pruefen.

    DAS GEGENSTUECK ZU darf_weg, UND ES HAT GENAUSO LANGE GEFEHLT. Eine Probe
    kann die Werkstatt nicht mehr loeschen, aber sie konnte bis zum 13.09.
    ungehindert ins echte Gedaechtnis SCHREIBEN - und hat es getan:
    pruefung_test.py legte bei JEDEM Lauf eine Zusammenfassung ueber "Lenas
    Arzttermin" ins echte gedaechtnis.db. Siebzehn Stueck lagen am Morgen
    darin, aus einer Sitzung (s-1789214400 = archiv_test.JETZT), die Calvin
    nie gefuehrt hat. Gefunden erst, als der Rueckblick sie erzaehlen sollte.

    archiv.abschliessen() sagt in seinem Docstring: "`merken` und `journal`
    sind Parameter, damit die Probe nicht ins echte Gedaechtnis schreibt.
    Zweimal ist an genau dieser Stelle heute schon eine Probe ins Echte
    gelaufen." Das war das dritte Mal. Ein Riegel in jeder Probe einzeln
    genuegt nicht - er gehoert an die Stelle, die schreibt.
    """
    if not eine_probe_laeuft() or _ausnahme_grund:
        return True
    p = Path(pfad).resolve()
    return not (p == ECHTE_WERKSTATT or _unter(p, ECHTE_WERKSTATT))


# Die einzige Tuer durch den Riegel - und sie ist absichtlich unbequem.
_ausnahme_grund = ""


class ausnahme:
    """EIN bewusst gewollter Schreibzugriff einer Probe ins Echte.

    Es gibt genau einen Fall, in dem eine Probe ins Echte schreiben MUSS:
    wenn sie ihre eigenen Spuren dort wieder wegnimmt. f5_test.py laesst den
    laufenden Bewohner einen Testtermin anlegen - das darf er, er ist keine
    Probe - und raeumt ihn danach weg. Ohne diese Tuer bliebe der Testtermin
    liegen, und der Riegel haette das Gegenteil dessen bewirkt, wofuer er da
    ist.

    WOFUER SIE NICHT DA IST: etwas hinzuzufuegen. Wer hier etwas anlegt, legt
    Calvin Erinnerungen an Gespraeche hin, die er nie gefuehrt hat - genau der
    Fehler, gegen den der Riegel steht. Der Grund ist Pflicht und steht im
    Abbruchtext, falls doch einmal etwas schiefgeht.

        with probenort.ausnahme("raeumt die eigenen Testtermine weg"):
            erinnern.schreiben(liste)
    """

    def __init__(self, grund: str):
        if not str(grund or "").strip():
            raise Verweigert("ABBRUCH: Eine Ausnahme ohne Grund gibt es nicht.")
        self.grund = grund

    def __enter__(self):
        global _ausnahme_grund
        self.vorher = _ausnahme_grund
        _ausnahme_grund = self.grund
        return self

    def __exit__(self, *_):
        global _ausnahme_grund
        _ausnahme_grund = self.vorher
        return False


def schreiben_pruefen(pfad, was: str = "") -> None:
    """Wirft, wenn eine Probe ins Echte schreiben will."""
    if darf_schreiben(pfad):
        return
    p = Path(pfad).resolve()
    raise Verweigert(
        f"ABBRUCH: Diese Probe wollte in {p} schreiben{' (' + was + ')' if was else ''}. "
        f"Das ist die ECHTE Ablage des Bewohners - eine Probe, die dort "
        f"schreibt, legt {NAME} Erinnerungen an Gespraeche hin, die er nie "
        f"gefuehrt hat. Hat die Probe ihre Ablage umzubiegen vergessen, oder "
        f"fehlt ein `merken=`-Parameter?")


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
