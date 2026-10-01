"""Trägt eine Entscheidung ihren Gegenstand?

    python -X utf8 gegenstand_test.py

"genehmigt" allein sagt nichts. Im Gedächtnis muss stehen, WAS genehmigt
wurde - die Zeile steht dort später allein da.
"""
from einstellungen import NAME
import json
import sys
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
import bewohner  # noqa: E402
import pruefstand  # noqa: E402

ok_alle = []
mitgeschrieben = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


# Journal abfangen, nichts Echtes anfassen.
echt_journal = bewohner.journal
bewohner.journal = lambda art, text, **e: mitgeschrieben.append((art, text))
echt_ordner = bewohner.ANTRAEGE
probe = pruefstand.probenordner("gegenstand")
bewohner.ANTRAEGE = probe

TITEL = "Den Ollama-Dienst neu starten dürfen"

print("Antrag stellen:")
kennung = bewohner.antrag_stellen({"title": TITEL, "reason": "weil er hängt"})
art, text = mitgeschrieben[-1]
pruefen("der Antrag nennt seinen Gegenstand", TITEL in text, text)
pruefen("und ist ein ganzer Satz", text.startswith("Ich habe beantragt"))

for stand in ("genehmigt", "abgelehnt"):
    print(f"\nEntscheidung '{stand}':")
    p = probe / f"{kennung}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["status"] = stand
    d.pop("_gelesen", None)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    mitgeschrieben.clear()
    bewohner.antraege_pruefen()
    art, text = mitgeschrieben[-1]
    pruefen(f"nennt den Gegenstand", TITEL in text, text)
    pruefen(f"nennt {NAME} als Entscheider", text.startswith(f"{NAME} hat"))
    pruefen(f"nennt den Ausgang", stand in text)

print("\nOhne Titel darf es nicht leer werden:")
p = probe / "a-ohnetitel.json"
p.write_text(json.dumps({"id": "a-ohnetitel", "ts": time.time(),
                         "title": "", "status": "genehmigt"}),
             encoding="utf-8")
mitgeschrieben.clear()
bewohner.antraege_pruefen()
texte = [t for a, t in mitgeschrieben if a == "entscheidung"]
pruefen("fällt auf die Kennung zurück",
        any("a-ohnetitel" in t for t in texte), texte[-1] if texte else "-")

bewohner.journal = echt_journal
bewohner.ANTRAEGE = echt_ordner
for f in probe.glob("*"):
    f.unlink()
probe.rmdir()
print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
