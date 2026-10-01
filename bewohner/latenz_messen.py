"""Wie lange bis zum ersten Ton? Eine Frage nach der anderen.

    python -X utf8 latenz_messen.py

Stellt Fragen mit "von": "test" und wartet jede Antwort ab, bevor die
naechste kommt - sonst steht Calvin hinter dem Test.
"""
import json
import sys
import time
from pathlib import Path

W = Path(__file__).parent / "werkstatt"
GESPRAECH = W / "gespraech"

FRAGEN = ["Kannst du mich hören?",
          "Wie geht es dir?",
          "Was hast du heute gemacht?"]


JOURNAL = W / "journal.jsonl"


def erkannt_um(kennung: str) -> float | None:
    """Wann hat pruefen() die Frage bemerkt? Steht als frage-Eintrag im
    Journal - dafuer muss nichts am Bewohner geaendert werden."""
    try:
        for z in reversed(JOURNAL.read_text(encoding="utf-8").splitlines()):
            e = json.loads(z)
            if e.get("kind") == "frage" and e.get("id") == kennung:
                return float(e.get("ts", 0))
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return None


def stellen(frage: str, frist: float = 180.0) -> dict:
    kennung = f"g-test-{int(time.time() * 1000)}"
    pfad = GESPRAECH / f"{kennung}.json"
    pfad.write_text(json.dumps(
        {"id": kennung, "ts": time.time(), "text": frage,
         "status": "offen", "von": "test"}, ensure_ascii=False),
        encoding="utf-8")
    t0 = time.time()
    erster_ton = None
    while time.time() - t0 < frist:
        time.sleep(0.3)
        # Erster Ton = erste MP3 zu dieser Frage.
        if erster_ton is None and list(GESPRAECH.glob(f"{kennung}-*.mp3")):
            erster_ton = time.time() - t0
        try:
            d = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if d.get("status") == "beantwortet":
            bemerkt = erkannt_um(kennung)
            return {"frage": frage, "antwort": d.get("antwort", ""),
                    "text_s": (d.get("antwort_ts") or time.time()) - t0,
                    "ton_s": erster_ton, "status": d.get("status"),
                    "bemerkt_s": (bemerkt - t0) if bemerkt else None}
    return {"frage": frage, "antwort": "(Zeitlimit)", "text_s": frist,
            "ton_s": erster_ton, "status": "?", "bemerkt_s": None}


print(f"{'Frage':30} {'bemerkt':>8} {'1. Ton':>8} {'fertig':>8}")
werte, bemerkt_werte = [], []
for f in FRAGEN:
    e = stellen(f)
    def z(w):
        return f"{w:.1f}s" if w else "-"
    print(f"{f[:30]:30} {z(e['bemerkt_s']):>8} {z(e['ton_s']):>8} "
          f"{z(e['text_s']):>8}")
    print(f"   -> {e['antwort'][:80]}")
    if e["ton_s"]:
        werte.append(e["ton_s"])
    if e["bemerkt_s"]:
        bemerkt_werte.append(e["bemerkt_s"])

if werte:
    print(f"\nerster Ton : Median {sorted(werte)[len(werte) // 2]:.1f}s   "
          f"Ziel <= 5 s")
if bemerkt_werte:
    m = sorted(bemerkt_werte)[len(bemerkt_werte) // 2]
    print(f"davon Warten, bis die Frage überhaupt bemerkt wurde: Median "
          f"{m:.1f}s")
