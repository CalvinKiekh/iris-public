"""What a probe needs before it can say anything - and how it says it cannot.

Most probes here check the code alone and run anywhere. Some need the
resident himself: his workshop with its journal, the tools he has been
given, the model he thinks with, or Windows, where he lives. Without that
they used to crash, or worse, end with 0 and look passed.

A probe that lacks what it needs now ends with UEBERSPRUNGEN (77, the code
automake and pytest use for "skipped") and one line saying what is missing.
pruefen.py counts that apart from passed and failed.

None of the checks creates anything. In particular `braucht_bewohner` only
looks: the workshop next to the code is the real one wherever the resident
lives, and a probe that made it would fool every probe after it.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

HIER = Path(__file__).parent
WERKSTATT = HIER / "werkstatt"
WERKZEUGE = WERKSTATT / "werkzeuge"

UEBERSPRUNGEN = 77


def ueberspringen(grund: str) -> None:
    print(f"  --  uebersprungen: {grund}")
    raise SystemExit(UEBERSPRUNGEN)


def bewohner_da() -> bool:
    """Lives a resident here? He writes his journal from the first minute on."""
    return (WERKSTATT / "journal.jsonl").is_file()


def braucht_bewohner(*dateien: str) -> None:
    """The real workshop, and in it the named files."""
    if not bewohner_da():
        ueberspringen("hier wohnt kein Bewohner (werkstatt/journal.jsonl fehlt)")
    fehlt = [d for d in dateien if not (WERKSTATT / d).exists()]
    if fehlt:
        ueberspringen("in der Werkstatt fehlt " + ", ".join(fehlt))


def werkzeug_da(name: str) -> bool:
    return (WERKZEUGE / f"{name}.py").is_file()


def braucht_werkzeug(*namen: str) -> None:
    """Tools he loads from werkstatt/werkzeuge - see einrichten.py."""
    fehlt = [n for n in namen if not werkzeug_da(n)]
    if fehlt:
        ueberspringen("Werkzeug nicht eingerichtet: " + ", ".join(fehlt)
                      + " (python einrichten.py)")


def braucht_windows() -> None:
    if sys.platform != "win32":
        ueberspringen("laeuft nur unter Windows")


def modell_da(modell: str = "gpt-oss:20b") -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags",
                                    timeout=5) as a:
            namen = {m.get("name") for m in json.load(a).get("models", [])}
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return modell in namen


def braucht_modell(modell: str = "gpt-oss:20b") -> None:
    """The real model, for probes that measure what it answers."""
    if not modell_da(modell):
        ueberspringen(f"Ollama mit {modell} antwortet nicht")


def werkzeuge_einbinden() -> None:
    """Make the tools importable for probes that test their code, not his
    installation: the workshop's copy where he lives, else the repo's."""
    for ort in (HIER / "werkzeuge", WERKZEUGE):
        if ort.is_dir() and str(ort) not in sys.path:
            sys.path.insert(0, str(ort))


def probenordner(name: str) -> Path:
    """A folder for a probe: werkstatt/_<name>_probe where he lives - probes
    there see what he sees - and a throwaway one anywhere else."""
    if bewohner_da():
        ort = WERKSTATT / f"_{name}_probe"
        ort.mkdir(exist_ok=True)
        return ort
    import probenort
    return probenort.ablage(name)
