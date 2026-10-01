"""Greifen die fünf Regeln aus Calvins Genehmigung?

    python -X utf8 eingriff_test.py

Nichts wird wirklich angefasst - geprüft werden die Entscheidungen.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import eingreifen

ok_alle = []


def pruefen(name, bedingung, dazu=""):
    ok_alle.append(bool(bedingung))
    print(f"  {'ok  ' if bedingung else 'FAIL'} {name}" + (f"  [{dazu}]" if dazu else ""))


print("Regel 1 - erst messen, dann eingreifen:")
pruefen("gesunde Lage -> kein Eingriff",
        eingreifen.noetig({"ollama": True, "tempo": 130, "waisen": []}) is None)
pruefen("Ollama weg -> Eingriff",
        eingreifen.noetig({"ollama": False, "tempo": None, "waisen": []})
        == "Ollama antwortet nicht")
pruefen("Waisen -> Eingriff",
        "verwaiste" in (eingreifen.noetig(
            {"ollama": True, "tempo": 130, "waisen": [1, 2]}) or ""))
pruefen("Tempoeinbruch -> Eingriff",
        "Token" in (eingreifen.noetig(
            {"ollama": True, "tempo": 6, "waisen": []}) or ""))
pruefen("langsam, aber nicht eingebrochen -> kein Eingriff",
        eingreifen.noetig({"ollama": True, "tempo": 90, "waisen": []}) is None)

# Ein fehlender Messwert heisst "ich weiss es nicht", nicht "tot". Am 12.09.
# genuegte ein falscher Funktionsname (selbst.bild statt selbst.lagebild),
# um ein leeres Lagebild zu erzeugen - und noetig() sagte "Ollama antwortet
# nicht". Ein Tippfehler haette den Dienst neu gestartet, mit dem er denkt.
pruefen("leeres Lagebild -> KEIN Eingriff",
        eingreifen.noetig({}) is None)
pruefen("ollama nicht gemessen -> KEIN Eingriff",
        eingreifen.noetig({"ollama": None, "tempo": None}) is None)
pruefen("gar kein Lagebild -> KEIN Eingriff",
        eingreifen.noetig(None) is None)
pruefen("aber gemessen und weg -> doch Eingriff",
        eingreifen.noetig({"ollama": False}) == "Ollama antwortet nicht")

print("\nRegel 2 - höchstens alle zehn Minuten:")
eingreifen._zuletzt = time.time()
erlaubt, grund = eingreifen.darf()
pruefen("kurz danach nicht wieder", not erlaubt, grund)
erlaubt, _ = eingreifen.darf(time.time() + 601)
pruefen("nach zehn Minuten wieder", erlaubt)

print("\nRegel 5 - nach zwei Fehlschlägen Schluss:")
eingreifen._zuletzt = 0.0
eingreifen._erfolglos = 2
eingreifen._gesperrt = True
erlaubt, grund = eingreifen.darf()
pruefen("gesperrt", not erlaubt, grund[:60])
eingreifen._erfolglos = 0
eingreifen._gesperrt = False

print("\nGrenze des Rechts - nur llama-server:")
fremd = eingreifen.waisen_beenden([os_pid := __import__("os").getpid()])
pruefen("beendet den eigenen Prozess NICHT", not fremd,
        f"PID {os_pid} blieb verschont")

print("\nTrockenlauf am echten System:")
e = eingreifen.eingreifen(trocken=True)
pruefen("fasst nichts an", not e["getan"], e["grund"][:70])

print(f"\n{sum(ok_alle)} von {len(ok_alle)} bestanden")
sys.exit(0 if all(ok_alle) else 1)
