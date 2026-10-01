"""Keine Claude-Sitzung auf Vorrat - sie entsteht beim ersten Auftrag.

    python -X utf8 sitzung_sparsam_test.py

Eine Claude-Sitzung ist ein Prozess. Der Bewohner legte beim Start eine an,
ob sie gebraucht wurde oder nicht, und niemand schloss sie: Am Abend des 12.09.
lagen nach acht Neustarts acht Sitzungen mit seq=0 da. Der Mac hat vier von
Hand geschlossen und seinen eigenen Waechter umgebaut, weil der Verdacht auf
ihn fiel - die Ursache war dieser Aufruf.

Geprueft wird ohne Bruecke: Das Anlegen fuehrt ueber _post("/api/sessions"),
und genau das darf beim Start nicht passieren.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}"
          + (f"  [{dazu}]" if dazu else ""))


quelle_bewohner = (HIER / "bewohner.py").read_text(encoding="utf-8")
quelle_chain = (HIER / "chain.py").read_text(encoding="utf-8")


print("\nDer Start legt keine Sitzung an")

# Jede Zeile, die sitzung_sichern() aufruft - ohne Kommentare.
aufrufe = [z.strip() for z in quelle_bewohner.splitlines()
           if "sitzung_sichern()" in z and not z.strip().startswith("#")]
pruefen("bewohner.py ruft sitzung_sichern() nirgends von sich aus auf",
        aufrufe == [], str(aufrufe))

pruefen("und der Grund steht als Kommentar da, nicht nur im Commit",
        "reine Verschwendung" in quelle_bewohner
        and "seq=0" in quelle_bewohner)


print("\nAber beauftrage() legt sie an, wenn wirklich ein Auftrag kommt")

pruefen("beauftrage() holt die Sitzung selbst",
        re.search(r"key = self\.key or self\.sitzung_sichern\(\)",
                  quelle_chain) is not None)
pruefen("self.key faengt als None an",
        "self.key: str | None = None" in quelle_chain)


print("\nUnd der lebenszeichen-Faden traegt den Schluessel nach")

pruefen("er liest den Schluessel bei jedem Puls",
        'getattr(self.bruecke, "key", None)' in quelle_bewohner)
pruefen("und schreibt nur, wenn es einen gibt",
        re.search(r"if schluessel and schluessel != self\.daten\.get\("
                  r"\"session_key\"\)", quelle_bewohner) is not None)
pruefen("bewohner.json faengt mit session_key None an",
        '"session_key": None' in quelle_bewohner)


print("\nDer Gegenbeweis: ohne diese Zeilen waere es nicht nachweisbar")

# Wenn jemand den Aufruf wieder einbaut, muss diese Probe es merken. Also
# einmal nachstellen, dass sie ihn auch findet.
nachgestellt = quelle_bewohner.replace(
    "    beobachter = Beobachter(bruecke)",
    "    bruecke.sitzung_sichern()\n    beobachter = Beobachter(bruecke)", 1)
wieder = [z.strip() for z in nachgestellt.splitlines()
          if "sitzung_sichern()" in z and not z.strip().startswith("#")]
pruefen("ein wieder eingebauter Aufruf wuerde auffallen", wieder != [],
        str(wieder))


print("\ncwd der Sitzung: die Werkstatt, und das mit Absicht")

pruefen('die Sitzung arbeitet in werkstatt\\, nicht im Quellbaum',
        'daten = {"cwd": str(WERKSTATT)}' in quelle_chain)
pruefen("und es ist benannt, nicht beilaeufig",
        "Ordner, in dem die Claude-Code-Sitzung arbeitet" in quelle_chain)
pruefen("der Systemtext sagt es ihr auch",
        "Sie arbeitet im Ordner {WERKSTATT}" in quelle_chain
        or "Sie arbeitet im Ordner" in quelle_chain)


print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
