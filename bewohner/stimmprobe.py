"""Hörprobe mit der von Calvin gewählten Stimme.

    python -X utf8 stimmprobe.py

Schreibt nach Desktop\\Stimmproben\\helmut-1.mp3 usw. Der Schlüssel wird nur
gelesen und taucht in keiner Meldung auf.
"""
import einstellungen
from einstellungen import NAME
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from gespraech import EL_MODELL, EL_SCHLUESSEL, EL_SPRACHE, EL_STIMME_ID

ZIEL = einstellungen.STIMMPROBEN
SAETZE = ["Ja, ich höre dich.",
          "Gut, alles ruhig.",
          f"{NAME} hat nach dem Platz auf C gefragt, das habe ich "
          "zurückgehalten, weil er selbst am Rechner war."]

if not EL_SCHLUESSEL.exists():
    sys.exit("Kein Schlüssel hinterlegt.")
s = EL_SCHLUESSEL.read_text(encoding="utf-8").strip()
ZIEL.mkdir(parents=True, exist_ok=True)

print(f"Stimme {EL_STIMME_ID}, Modell {EL_MODELL}, Sprache {EL_SPRACHE}\n")
for nr, satz in enumerate(SAETZE, 1):
    ziel = ZIEL / f"helmut-{nr}.mp3"
    t0 = time.time()
    erstes = None
    stuecke = []
    try:
        with httpx.stream(
            "POST",
            f"https://api.elevenlabs.io/v1/text-to-speech/"
            f"{EL_STIMME_ID}/stream?output_format=mp3_44100_128",
            headers={"xi-api-key": s}, timeout=120,
            json={"text": satz, "model_id": EL_MODELL,
                  "language_code": EL_SPRACHE},
        ) as r:
            r.raise_for_status()
            for b in r.iter_bytes():
                if b and erstes is None:
                    erstes = time.time() - t0
                stuecke.append(b)
    except httpx.HTTPError as f:
        rumpf = ""
        if getattr(f, "response", None) is not None:
            rumpf = f.response.text.replace(s, "***")[:200]
        print(f"  Satz {nr}: Fehler {type(f).__name__} {rumpf}")
        continue
    ziel.write_bytes(b"".join(stuecke))
    print(f"  Satz {nr}: erstes Byte {erstes:.2f}s, gesamt "
          f"{time.time() - t0:.2f}s, {ziel.stat().st_size // 1024} KB "
          f"-> {ziel.name}")

r = httpx.get("https://api.elevenlabs.io/v1/user/subscription",
              headers={"xi-api-key": s}, timeout=30).json()
print(f"\nKontingent: {r.get('character_count')} von "
      f"{r.get('character_limit')} Zeichen")
