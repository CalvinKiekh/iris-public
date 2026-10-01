"""Was am Bewohner vom Menschen und vom Rechner abhaengt - an einer Stelle.

Bis zum 28.09.2026 stand das verstreut im Code: der Name in rund 250 Saetzen,
die einem Modell sagen, fuer wen es da ist, und feste Pfade in den
Heimatordner eines bestimmten Windows-Kontos, in einem Dutzend Dateien. Wer iris uebernimmt, haette jeden davon finden
muessen - und die Schutzregel gegen Schreiben ausserhalb der Werkstatt haette
bei ihm auf einen fremden Ordner gezeigt, also nichts geschuetzt.

Gelesen aus ~/.config/iris/config.json, derselben Datei wie die Bruecke:

    "nutzer":   {"name": "Calvin"}
    "bewohner": {"tts": "C:\\\\Users\\\\...\\\\tts-test"}    # optional

Alles andere ergibt sich aus dem Heimatordner. Die Werkstatt liegt ohnehin
neben dem Code (werkstatt/).

Beim Import gelesen, nicht bei jedem Aufruf: der Bewohner ist ein Prozess,
und wer den Namen aendert, startet ihn neu - wie jede andere Einstellung.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

HEIM = Path.home()
KONFIG = HEIM / ".config" / "iris" / "config.json"


def _konfig() -> dict:
    try:
        return json.loads(KONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_K = _konfig()
_B = _K.get("bewohner") or {}


def _vorname() -> str:
    """Der Name aus der Konfiguration, sonst der des Kontos.

    Der Kontoname ist nur ein Notbehelf, und oft ein falscher: unter Windows
    heisst das Konto gern verkuerzt ("calvi" statt Calvin). Darum steht der
    Name in config.json und wird dort gepflegt, nicht hier geraten.
    """
    name = (_K.get("nutzer") or {}).get("name")
    if name:
        return name
    konto = os.environ.get("USERNAME") or os.environ.get("USER") or "Nutzer"
    return konto[:1].upper() + konto[1:]


NAME = _vorname()
# Genitiv: Calvins, aber Hans' und Max'.
NAMENS = NAME + ("\u2019" if NAME[-1:].lower() in "s\u00dfxz" else "s")

# Wie der Mensch in gespeicherten Daten heisst: als Sprecher ("von"), als
# Herkunft einer Erinnerung, im Namen einiger Schluessel fuer das Modell.
# Aus dem Namen abgeleitet, damit alles, was vor dieser Einstellung schon
# geschrieben wurde, gueltig bleibt - fuer Calvin ist das "calvin", genau wie
# vorher, ohne dass ein Gespraech oder eine Erinnerung umgeschrieben werden
# muss. Die Kehrseite: den Namen spaeter zu aendern, trennt den Bewohner von
# allem, was er bis dahin ueber diesen Menschen gespeichert hat.
NUTZER = NAME.lower()

# --- Orte auf diesem Rechner -------------------------------------------------

# Die Sprachausgabe: ihre venv, die Stimmprobe, die sie nachspricht.
TTS = Path(_B.get("tts") or HEIM / "tts-test")
STIMME = TTS / "stimme.wav"

DESKTOP = HEIM / "Desktop"
DOWNLOADS = HEIM / "Downloads"
STIMMPROBEN = DESKTOP / "Stimmproben"

# Schluessel fuer die Sprachausgabe von ElevenLabs, neben der iris-Konfiguration.
EL_SCHLUESSEL = KONFIG.parent / "elevenlabs.key"
# Welche ElevenLabs-Stimme spricht. Eine oeffentliche aus deren Bibliothek,
# keine geheime Angabe - aber eine Vorliebe, also einstellbar.
EL_STIMME_ID = _B.get("stimme_id") or "g1jpii0iyvtRs8fqXsd1"


def ffmpeg() -> str:
    """ffmpeg auf dem Suchpfad, sonst die Stelle, an die winget es legt."""
    gefunden = shutil.which("ffmpeg")
    if gefunden:
        return gefunden
    pakete = HEIM / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    for kandidat in sorted(pakete.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe")):
        return str(kandidat)
    return "ffmpeg"


def ausserhalb_der_werkstatt() -> str:
    """Muster fuer Quelltext, der in den Heimatordner schreibt, nicht in die
    Werkstatt. Der Pfad kann dort einfach oder mit verdoppelten Backslashes
    stehen - in einem Python-String ist er meist verdoppelt."""
    teile = [re.escape(t) for t in re.split(r"[\\/]+", str(HEIM)) if t]
    trenner = r"[\\/]{1,2}"
    kopf = (teile[0] + trenner) if re.fullmatch(r"[A-Za-z]:", str(HEIM)[:2]) else trenner + teile[0] + trenner
    rumpf = trenner.join(teile[1:])
    return kopf + rumpf + trenner + r"(?!.*werkstatt)"
