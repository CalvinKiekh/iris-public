"""Stimmen in Zahlen - Tonhöhe, Klangfarbe, Tempo, Pausen, Dynamik.

    python -X utf8 stimme_messen.py

Nicht transkribieren, sondern messen. Er soll begründen können, was ihm
passt, statt eine Stimme nach Gefühl zu wählen. Umgestellt wird nichts -
ein Vorschlag an Calvin ist ein Antrag.
"""
import einstellungen
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

PROBEN = einstellungen.STIMMPROBEN
FFMPEG = einstellungen.ffmpeg()


def laden(p: Path):
    """MP3 über ffmpeg nach WAV, dann lesen."""
    if p.suffix.lower() == ".wav":
        return sf.read(str(p))
    ziel = Path(tempfile.gettempdir()) / (p.stem + "_probe.wav")
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(p),
                    "-ac", "1", str(ziel)], timeout=120,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    daten, rate = sf.read(str(ziel))
    ziel.unlink(missing_ok=True)
    return daten, rate


def tonhoehe(welle, rate) -> tuple[float, float]:
    """Grundfrequenz je Fenster über Autokorrelation. Median und Spanne."""
    fenster = int(rate * 0.04)
    schritte = []
    for i in range(0, len(welle) - fenster, fenster):
        stueck = welle[i:i + fenster]
        if np.sqrt(np.mean(stueck ** 2)) < 0.01:
            continue                      # zu leise, keine Stimme
        stueck = stueck - np.mean(stueck)
        k = np.correlate(stueck, stueck, mode="full")[fenster - 1:]
        # 70 bis 400 Hz ist der Bereich menschlicher Sprechstimmen.
        von, bis = int(rate / 400), int(rate / 70)
        if bis >= len(k):
            continue
        spitze = np.argmax(k[von:bis]) + von
        if spitze > 0:
            schritte.append(rate / spitze)
    if not schritte:
        return 0.0, 0.0
    return float(np.median(schritte)), float(np.percentile(schritte, 90) -
                                             np.percentile(schritte, 10))


def schwerpunkt(welle, rate) -> float:
    """Spektralschwerpunkt - hoch heißt hell, tief heißt dunkel."""
    spektrum = np.abs(np.fft.rfft(welle))
    frequenzen = np.fft.rfftfreq(len(welle), 1 / rate)
    if spektrum.sum() <= 0:
        return 0.0
    return float((spektrum * frequenzen).sum() / spektrum.sum())


def pausen(welle, rate) -> tuple[float, int]:
    """Anteil Stille und Anzahl der Pausen über 150 ms."""
    fenster = int(rate * 0.02)
    laut = np.array([np.sqrt(np.mean(welle[i:i + fenster] ** 2)) > 0.01
                     for i in range(0, len(welle) - fenster, fenster)])
    if not len(laut):
        return 0.0, 0
    still = 1.0 - laut.mean()
    n, lauf = 0, 0
    for x in laut:
        if not x:
            lauf += 1
        else:
            if lauf * 0.02 >= 0.15:
                n += 1
            lauf = 0
    return float(still), n


def messen(p: Path) -> dict:
    welle, rate = laden(p)
    if welle.ndim > 1:
        welle = welle.mean(axis=1)
    mitte, spanne = tonhoehe(welle, rate)
    still, n = pausen(welle, rate)
    laut = np.abs(welle)
    return {"datei": p.name,
            "dauer_s": round(len(welle) / rate, 2),
            "tonhoehe_hz": round(mitte, 1),
            "spanne_hz": round(spanne, 1),
            "schwerpunkt_hz": round(schwerpunkt(welle, rate)),
            "stille_anteil": round(still, 2),
            "pausen": n,
            "dynamik": round(float(np.percentile(laut, 95) /
                                   (np.percentile(laut, 50) + 1e-9)), 1)}


if __name__ == "__main__":
    dateien = sorted(PROBEN.glob("*.mp3"))
    if not dateien:
        sys.exit(f"Keine Proben unter {PROBEN}")
    print(f"{'Datei':32} {'Dauer':>6} {'Tonhöhe':>8} {'Spanne':>7} "
          f"{'Klang':>7} {'Stille':>7} {'Dyn':>5}")
    for p in dateien:
        try:
            m = messen(p)
        except Exception as f:
            print(f"{p.name:32} nicht messbar ({type(f).__name__})")
            continue
        print(f"{m['datei'][:32]:32} {m['dauer_s']:5.1f}s "
              f"{m['tonhoehe_hz']:7.0f} {m['spanne_hz']:6.0f} "
              f"{m['schwerpunkt_hz']:6d} {m['stille_anteil']:6.2f} "
              f"{m['dynamik']:5.1f}")
