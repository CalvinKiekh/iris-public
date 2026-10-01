"""Deutsche Sprachausgabe, gebrauchsfertig.

    python sprich.py "Text den du hoeren willst"
    python sprich.py --datei text.txt
    echo "Text" | python sprich.py

Zerlegt den Text in Saetze und spricht sie einzeln. Das umgeht die
Wiederholungsschleife, in die Chatterbox bei langen Saetzen geraet - und
erlaubt spaeter Streaming, weil Satz 1 schon klingt waehrend Satz 2 rechnet.
"""

import argparse
import re
import sys
import time
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

from normalisieren import normalisieren

HIER = Path(__file__).parent
STIMME = HIER / "stimme.wav"          # Referenzstimme
PAUSE_MS = 250                        # Stille zwischen Saetzen

# Gewaehlte Einstellung: "z3_mitte" - die Mitte zwischen einer lebendigen und
# einer moeglichst referenztreuen Variante. Ausgewaehlt durch Hoervergleich von
# 16 Varianten plus 5 Zwischenstufen am 11.09.2026.
#
# Die Voreinstellungen von Chatterbox (0.5 / 0.5 / 0.8 / 2.0) gehen auf
# "lebendig" statt "aehnlich" und wurden verworfen.
REGLER = dict(
    exaggeration=0.325,        # Ausdruck - hoeher wirkt lebendiger, trifft aber schlechter
    cfg_weight=0.775,          # Treue zur Referenzstimme
    temperature=0.6,           # Zufall - ueber 0.8 haengt das Modell Muell an
    repetition_penalty=1.4,    # unter 1.2 bricht es zu frueh ab
    min_p=0.075,
    top_p=0.95,
)


def referenz_aufbereiten(pfad: Path, ziel: Path, entrauschen: bool = False,
                         staerke: float = 0.6, sekunden: float | None = 30.0) -> Path:
    """Beliebiges Format -> mono WAV, entrauscht, getrimmt, Pegel angehoben.

    Das Modell klont alles, was im Clip steckt - auch Atemgeraeusche und
    Grundrauschen. Reihenfolge ist wichtig: erst entrauschen, dann trimmen
    (weil Stille danach leiser ist), zuletzt anheben.
    """
    audio, sr = librosa.load(str(pfad), sr=None, mono=True)
    vorher = len(audio) / sr
    spitze_roh = float(np.abs(audio).max())

    if entrauschen:
        import noisereduce as nr
        # prop_decrease unter 1.0 laesst etwas Rauschen stehen. Voll
        # entrauscht klingt metallisch, und das wuerde mitgeklont.
        audio = nr.reduce_noise(y=audio, sr=sr, prop_decrease=staerke,
                                stationary=True)

    # top_db=45 statt 30: schneidet nur wirklich Stilles weg. Ein leiser
    # Satzanfang liegt schnell 30 dB unter der lautesten Stelle und wuerde
    # sonst mit abgeschnitten.
    beschnitten, grenzen = librosa.effects.trim(audio, top_db=45)
    # 200 ms Sicherheitsabstand vor dem erkannten Anfang stehen lassen.
    puffer = int(0.2 * sr)
    start = max(0, int(grenzen[0]) - puffer)
    ende = min(len(audio), int(grenzen[1]) + puffer)
    audio = audio[start:ende]

    spitze = float(np.abs(audio).max())
    if 0 < spitze < 0.5:
        audio = audio * (0.9 / spitze)

    # `sekunden=None` laesst die Aufnahme ganz. Chatterbox schneidet den
    # Prompt intern selbst zu, aber die Sprecher-Einbettung wird ueber das
    # gesamte uebergebene Audio gemittelt - mehr Material heisst dort eine
    # stabilere Stimme.
    if sekunden:
        audio = audio[: int(sekunden * sr)]
    sf.write(str(ziel), audio, sr)
    print(f"Referenz: {pfad.name}  {vorher:.1f}s -> {len(audio) / sr:.1f}s, "
          f"Spitze {spitze_roh:.2f} -> {float(np.abs(audio).max()):.2f}"
          + (f", entrauscht ({staerke})" if entrauschen else ""))
    return ziel


# Nur Zahlen gelten als Anweisung. Vorher stand hier `\{([^}]*)\}`, und ein
# beilaeufiges "{Hinweis}" im Text zerriss den Satz in drei Stuecke.
BETONUNG = re.compile(r"\{\s*(\d*\.?\d*(?:\s*/\s*\d*\.?\d+)?)\s*\}")


def betonung_zerlegen(text: str, grund: dict) -> list[tuple[str, dict]]:
    """Zerlegt in Saetze und haengt an jeden seine eigenen Regler.

    Chatterbox kennt KEINE Tag-Sprache. Klammern, eckige Klammern und
    Sternchen landen im Text und werden mitgesprochen - gemessen am
    14.09.2026: derselbe Satz mit "(fluesternd)" davor wurde eine Sekunde
    laenger, also genau um das ausgesprochene Wort.

    Weil der Text ohnehin Satz fuer Satz erzeugt wird, geht Betonung aber
    ueber die Regler. Geschweifte Klammern setzen sie um und werden aus dem
    gesprochenen Text entfernt:

        {0.8} ab hier ausdrucksstaerker
        {0.8/0.6} Ausdruck und Treue zugleich
        {} zurueck auf die Grundeinstellung

    Geschweifte Klammern deshalb, weil runde in normalem Text vorkommen -
    die soll er weiter vorlesen duerfen.
    """
    stellen, letzte, teile = list(BETONUNG.finditer(text)), 0, []
    regler = dict(grund)
    for m in stellen:
        vorher = text[letzte:m.start()].strip()
        if vorher:
            teile.append((vorher, dict(regler)))
        roh = m.group(1).strip()
        if not roh:                      # {} setzt zurueck
            regler = dict(grund)
        else:
            zahlen = [z.strip() for z in roh.split("/")]
            try:
                regler = dict(regler, exaggeration=float(zahlen[0]))
                if len(zahlen) > 1:
                    regler["cfg_weight"] = float(zahlen[1])
            except ValueError:
                # Kein Zahlenpaar - dann war es wohl echter Text in
                # geschweiften Klammern. Stehen lassen und sprechen.
                teile.append(("{" + roh + "}", dict(regler)))
        letzte = m.end()
    rest = text[letzte:].strip()
    if rest:
        teile.append((rest, dict(regler)))

    raus = []
    for stueck, r in teile:
        for satz in in_saetze(stueck):
            raus.append((satz, r))
    return raus


def in_saetze(text: str) -> list[str]:
    """Zerlegt an Satzzeichen, haelt Abkuerzungen zusammen."""
    # Der Normalisierer hat Abkuerzungen schon aufgeloest, daher ist ein
    # einfacher Schnitt hier sicher.
    roh = re.split(r"(?<=[.!?])\s+", text.strip())
    saetze = []
    for s in roh:
        s = s.strip()
        if not s:
            continue
        # Sehr lange Saetze zusaetzlich an Kommas teilen.
        if len(s) > 200:
            teile = re.split(r"(?<=,)\s+", s)
            puffer = ""
            for t in teile:
                if len(puffer) + len(t) > 200 and puffer:
                    saetze.append(puffer.strip())
                    puffer = t
                else:
                    puffer += " " + t
            if puffer.strip():
                saetze.append(puffer.strip())
        else:
            saetze.append(s)
    return saetze


def main() -> None:
    p = argparse.ArgumentParser(description="Deutsche Sprachausgabe")
    p.add_argument("text", nargs="*", help="Was gesprochen werden soll")
    p.add_argument("--datei", help="Text aus Datei lesen")
    p.add_argument("--stimme", default=str(STIMME), help="Referenzaudio")
    p.add_argument("--ziel", default=str(HIER / "ausgabe.wav"))
    p.add_argument("--roh", action="store_true",
                   help="Ohne Normalisierung sprechen")
    p.add_argument("--ausdruck", type=float, default=REGLER["exaggeration"])
    p.add_argument("--treue", type=float, default=REGLER["cfg_weight"])
    p.add_argument("--zufall", type=float, default=REGLER["temperature"])
    p.add_argument("--entrauschen", action="store_true",
                   help="Rauschunterdrueckung auf die Referenz anwenden")
    p.add_argument("--staerke", type=float, default=0.6,
                   help="Wie stark entrauscht wird (0.0-1.0)")
    args = p.parse_args()

    if args.datei:
        text = Path(args.datei).read_text(encoding="utf-8")
    elif args.text:
        text = " ".join(args.text)
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        p.error("Kein Text angegeben.")

    if not args.roh:
        text = normalisieren(text)

    saetze = in_saetze(text)
    print(f"{len(saetze)} Satz/Saetze\n")

    quelle = Path(args.stimme)
    if not quelle.exists():
        sys.exit(f"Referenzstimme fehlt: {quelle}\n"
                 f"Lege eine Aufnahme dort ab (20-30s, sauber, eine Person).")
    referenz = referenz_aufbereiten(quelle, HIER / "_referenz_bereit.wav", args.entrauschen, args.staerke)

    regler = dict(REGLER)
    regler.update(exaggeration=args.ausdruck, cfg_weight=args.treue,
                  temperature=args.zufall)
    print("Regler  : " + "  ".join(f"{k}={v}" for k, v in regler.items()) + "\n")

    geraet = "cuda" if torch.cuda.is_available() else "cpu"
    modell = ChatterboxMultilingualTTS.from_pretrained(device=geraet)

    stuecke = []
    stille = np.zeros(int(modell.sr * PAUSE_MS / 1000), dtype=np.float32)
    gesamt = time.time()

    for i, satz in enumerate(saetze, 1):
        t0 = time.time()
        wav = modell.generate(satz, language_id="de",
                              audio_prompt_path=str(referenz), **regler)
        stueck = wav.cpu().numpy().astype(np.float32).squeeze()
        stuecke.append(stueck)
        if i < len(saetze):
            stuecke.append(stille)
        print(f"  [{i}/{len(saetze)}] {time.time() - t0:.1f}s  {satz[:60]}")

    alles = np.concatenate(stuecke)
    sf.write(args.ziel, alles, modell.sr)

    laenge = len(alles) / modell.sr
    dauer = time.time() - gesamt
    print(f"\n{laenge:.1f}s Audio in {dauer:.1f}s (Faktor {laenge / dauer:.1f}x)")
    print(f"-> {args.ziel}")


if __name__ == "__main__":
    main()

