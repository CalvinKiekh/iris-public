"""Was kostet gpt-oss allein? Untergrenze ohne Tick, ohne Stimme.

    python -X utf8 gptoss_untergrenze.py
"""
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from gespraech import OLLAMA, REDE_MODELL, SYSTEM

FAELLE = [
    ("leer, ein Wort", [{"role": "user", "content": "Sag nur: Ja."}]),
    ("SYSTEM + kurz", [{"role": "system", "content": SYSTEM},
                       {"role": "user", "content": "Kannst du mich hören?"}]),
]

print(f"{'Fall':18} {'1. Token':>9} {'gesamt':>8} {'Prompt':>8} {'Denken':>8} "
      f"{'Tok/s':>7}")
for name, nachrichten in FAELLE:
    for runde in (1, 2):
        t0 = time.time()
        erstes = None
        letzte = {}
        with httpx.stream("POST", OLLAMA, timeout=300,
                          json={"model": REDE_MODELL, "messages": nachrichten,
                                "stream": True, "keep_alive": "30m",
                                "think": "low"}) as r:
            for zeile in r.iter_lines():
                if not zeile.strip():
                    continue
                try:
                    t = json.loads(zeile)
                except json.JSONDecodeError:
                    continue
                if (t.get("message", {}).get("content") or "") and erstes is None:
                    erstes = time.time() - t0
                if t.get("done"):
                    letzte = t
                    break
        gesamt = time.time() - t0
        p_ms = float(letzte.get("prompt_eval_duration", 0)) / 1e9
        e_ms = float(letzte.get("eval_duration", 0)) / 1e9
        n = int(letzte.get("eval_count", 0))
        tempo = n / e_ms if e_ms > 0 else 0
        # Denkzeit = alles vor dem ersten sprechbaren Zeichen, ohne Prompt.
        denken = (erstes or 0) - p_ms
        print(f"{name if runde == 2 else name + ' (kalt)':18} "
              f"{erstes or 0:8.2f}s {gesamt:7.2f}s {p_ms:7.2f}s "
              f"{max(denken, 0):7.2f}s {tempo:6.0f}")
