"""Zeigt, was der Bewohner über sich selbst misst.

    python -X utf8 selbst_messung.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import selbst

b = selbst.lagebild()
print(f"Ollama erreichbar : {b['ollama']}")
print(f"Tempo             : {b['tempo']} Token/s")
print(f"Nachsehen         : {b['ticks_je_minute']} Mal je Minute")
print(f"verwaiste Runner  : {b['waisen'] or 'keine'}")
print("Grafikspeicher je Prozess:")
for p in b["gpu"]:
    print(f"  {p['name'][:38]:38} dediziert {p['dediziert']:6d} MiB   "
          f"geteilt {p['geteilt']:6d} MiB")

f = selbst.befunde(b)
print(f"\nBefunde: {len(f)}")
for x in f:
    print(f"  - {x['text']}")
    print(f"    Vermutung: {x['vermutung']}")
    print(f"    außerhalb der Werkstatt: {x['ausserhalb']}")
if not f:
    print("  keine - alles im Rahmen")
