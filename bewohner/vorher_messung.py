"""Sieht er einen Rueckgang, den ihm niemand vorrechnet?

verbot_test.py stellt die Lage so:

    {"platte": {"C": "frei 41 GB, vorher 61 GB"}}

Der Rueckgang steht als Satz im Prompt. Im Betrieb liefert Beobachter._platte()
aber nur eine Zahl:

    {"frei_gb": 1535}

und Beobachter.veraendert() gibt als "veraendert" nur den SCHLUESSELNAMEN
zurueck, nicht den alten Wert:

    unterschiede = [k for k in neu if neu.get(k) != self.letzter.get(k)]

Diese Probe stellt beide Formen derselben Lage gegenueber, sonst alles gleich.
Faellt die realistische Form deutlich ab, misst verbot_test.py eine Lage, die
im Betrieb nie vorkommt - und dann fehlt ihm nicht die Erlaubnis und nicht die
Schwelle, sondern der Vergleichswert.

    python vorher_messung.py
"""
from __future__ import annotations

import pruefstand

import bewohner

# Dieselbe Lage in drei Fassungen. Die Schluessel der realistischen Fassungen
# sind die echten aus Beobachter.blick() - "platte" heisst dort "frei_gb".
FASSUNGEN = [
    ("Probe-Fassung (vorher im Text)", ["platte"],
     {"platte": {"C": "frei 41 GB, vorher 61 GB"},
      "ollama": "ok", "prozesse": ["ollama.exe"], "modelle": 18}),

    ("echte Fassung (nur der Wert)", ["frei_gb"],
     {"frei_gb": 41,
      "ollama": "ok", "prozesse": ["ollama.exe"], "modelle": 18}),

    ("echte Fassung + vorher", ["frei_gb: 41, vorher 61"],
     {"frei_gb": 41,
      "ollama": "ok", "prozesse": ["ollama.exe"], "modelle": 18}),
]

ERWARTET = "platzverlauf"
VERSUCHE = 5


def main() -> int:
    pruefstand.braucht_modell()
    print("Probe: braucht er das Vorher?")

    ergebnisse = []
    for name, unterschiede, blick in FASSUNGEN:
        getroffen = []
        for _ in range(VERSUCHE):
            a = bewohner.frage_gpt_oss(blick, unterschiede, [], None)
            getroffen.append((a.get("selbst") or "").strip() or None)
        treffer = sum(1 for g in getroffen if g == ERWARTET)
        ergebnisse.append((name, treffer))
        print("  %-32s %d von %d -> %s" % (name, treffer, VERSUCHE, getroffen))

    print()
    probe = ergebnisse[0][1]
    echt = ergebnisse[1][1]
    mit = ergebnisse[2][1]
    if echt < probe and mit >= probe:
        print("  BEFUND: Das Vorher entscheidet. Ohne Vergleichswert greift er")
        print("          seltener zu (%d statt %d von %d); traegt man es nach,"
              % (echt, probe, VERSUCHE))
        print("          kommt er auf %d von %d zurueck." % (mit, VERSUCHE))
        print("          -> veraendert muss vorher UND jetzt nennen.")
    elif echt >= probe:
        print("  BEFUND: Das Vorher entscheidet NICHT. Die echte Fassung ist")
        print("          nicht schlechter (%d gegen %d von %d) - dann liegt es"
              % (echt, probe, VERSUCHE))
        print("          an der Streuung, nicht am fehlenden Vergleichswert.")
    else:
        print("  BEFUND: unklar. Echt %d, Probe %d, echt+vorher %d von %d."
              % (echt, probe, mit, VERSUCHE))
        print("          Stichprobe zu klein fuer eine Aussage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
