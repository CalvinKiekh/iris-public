"""Wo stecken die 5,4 Sekunden bis zum ersten Sprechbrocken?

    python zeitfresser.py

Fragt dreimal mit den echten Gespraechsnachrichten und haelt fest, was
Ollama meldet - plus die Zeit bis zum ersten Content-Token aus dem Strom.
"""

import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from bewohner import vorgaenge                       # noqa: E402
from gespraech import OLLAMA, REDE_MODELL, SYSTEM    # noqa: E402

FRAGEN = ["Erzähl mir in drei Sätzen, wie du arbeitest.",
          "Was war heute so los?",
          "Wie geht es dir gerade?"]


def kontext() -> str:
    b = vorgaenge()
    return json.dumps({"zustand": "wach", "bremse": None,
                       "leere_durchgaenge": b["nachgesehen"],
                       "vorgaenge": b["vorgaenge"]}, ensure_ascii=False)[:3000]


def einmal(frage: str) -> None:
    nachrichten = [{"role": "system", "content": SYSTEM},
                   {"role": "user", "content": f"{frage}\n\n[Lage]\n{kontext()}"}]

    # --- Strom: wann kommt das erste sprechbare Zeichen? ---
    t0 = time.time()
    erstes_denk = erstes_content = None
    denk_zeichen = 0
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
            m = t.get("message", {})
            denk = m.get("thinking") or ""
            inhalt = m.get("content") or ""
            if denk:
                denk_zeichen += len(denk)
                if erstes_denk is None:
                    erstes_denk = time.time() - t0
            if inhalt and erstes_content is None:
                erstes_content = time.time() - t0
            if t.get("done"):
                letzte = t
                break
    gesamt = time.time() - t0

    def s(schluessel: str) -> float:
        return float(letzte.get(schluessel, 0)) / 1e9

    print(f"\n--- {frage[:50]} ---")
    print(f"  bis erstes Denk-Token   {erstes_denk if erstes_denk else 0:6.2f}s")
    print(f"  bis erstes Content-Token{erstes_content if erstes_content else 0:6.2f}s"
          f"   <<< das zaehlt")
    print(f"  gesamt                  {gesamt:6.2f}s")
    print(f"  Denk-Zeichen            {denk_zeichen:6d}")
    print(f"  load_duration           {s('load_duration'):6.2f}s")
    print(f"  prompt_eval_count       {letzte.get('prompt_eval_count', 0):6d} Token")
    print(f"  prompt_eval_duration    {s('prompt_eval_duration'):6.2f}s")
    print(f"  eval_count              {letzte.get('eval_count', 0):6d} Token")
    print(f"  eval_duration           {s('eval_duration'):6.2f}s")
    if s("eval_duration") > 0:
        print(f"  Tempo                   {letzte.get('eval_count', 0) / s('eval_duration'):6.1f} Tok/s")


print(f"Modell: {REDE_MODELL}")
print(f"Kontextlaenge: {len(kontext())} Zeichen")
for f in FRAGEN:
    einmal(f)
