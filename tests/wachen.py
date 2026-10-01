"""Wachen: Messreihe, Stillstand, Budget - und wer davon geweckt wird.

    python3 -m tests.wachen

Geprueft wird ohne Netz und ohne Claude. Die Wache ist eine Datei, das
Wecken ein Griff, den der Manager hinterlegt - beides laesst sich hier
nachstellen.

Der Punkt, um den es eigentlich geht, ist `stillstand`: wer seit zwanzig
Zuegen an einer Optimierung sitzt, merkt selbst nicht mehr, dass es seit
drei Runden nicht besser wird. Genau dafuer gibt es den Vorarbeiter, also
muss genau das hier stimmen.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import wachen

ok_count = 0
fehler = []


def pruefe(bedingung, was, dazu=""):
    global ok_count
    if bedingung:
        ok_count += 1
        print(f"  ok   {was}")
    else:
        fehler.append(was)
        print(f"  FAIL {was}" + (f" ({dazu})" if dazu else ""))


# Eigenes Verzeichnis, damit nichts im Bestand angefasst wird.
wachen.DIR = tempfile.mkdtemp(prefix="iris-wachen-")

geweckt = []
wachen.configure(lambda key, text: geweckt.append((key, text)) or True)

print("Eine Wache anlegen")
w = wachen.neu("Belichtung fuer die Posenerkennung", sitzung="t-abc",
               vorarbeiter="vor-1", mass="ms je Bild", budget=5)
pruefe(w["stand"] == "laeuft", "sie laeuft")
pruefe(w["id"].startswith("belichtung-fuer-die-posenerkennung"),
       "die Kennung nennt das Ziel", w["id"])
pruefe(wachen.fuer_sitzung("t-abc") is not None, "sie haengt an ihrer Sitzung")
pruefe(wachen.fuer_sitzung("t-xyz") is None, "und an keiner anderen")

print("Runden eintragen")
for wert in (118, 64, 41):
    wachen.runde(w["id"], wert)
w = wachen.fuer_sitzung("t-abc")
pruefe(len(w["runden"]) == 3, "drei Runden stehen drin")
pruefe([r["wert"] for r in w["runden"]] == [118, 64, 41], "in der Reihenfolge")
pruefe(not wachen.stillstand(w), "solange es besser wird, ist das kein Stillstand")

print("Stillstand")
for wert in (41, 41, 40):
    wachen.runde(w["id"], wert)
w = wachen.fuer_sitzung("t-abc")
pruefe(wachen.stillstand(w), "drei Runden ohne Verbesserung faellt auf")
# 41 -> 40 sind 2,4 Prozent. Rechnerisch besser, in der Sache Rauschen - und
# genau daran laeuft eine Optimierung sonst ewig weiter.
pruefe(wachen.stillstand(w, schwelle=0.0) is False,
       "ohne Schwelle gaelte dasselbe als Fortschritt")

print("Ein echter Fortschritt beendet den Stillstand")
wachen.runde(w["id"], 29)
w = wachen.fuer_sitzung("t-abc")
pruefe(not wachen.stillstand(w), "eine bessere Zahl loest ihn auf")

print("Budget")
pruefe(wachen.budget_verbraucht(w), "sieben Runden bei Budget fuenf ist verbraucht",
       str(len(w["runden"])))

print("Der Bericht, so wie ein Modell ihn sieht")
b = wachen.bericht(w)
pruefe("Ziel: Belichtung" in b, "das Ziel steht drin")
pruefe("ms je Bild" in b, "das Mass auch")
pruefe("29" in b, "und die letzte Zahl")

print("Wer geweckt wird, wenn ein Zug endet")
geweckt.clear()
wachen.nach_zug("t-abc", "Bin bei 29 ms. Weiter?")
pruefe(len(geweckt) == 1, "der Vorarbeiter, genau einmal", str(len(geweckt)))
pruefe(geweckt and geweckt[0][0] == "vor-1", "und zwar seiner")
pruefe(geweckt and "29" in geweckt[0][1], "der Auftrag traegt die Messreihe")
pruefe(geweckt and "Budget ist aufgebraucht" in geweckt[0][1],
       "und nennt den Anlass")

print("Eine Sitzung ohne Wache weckt niemanden")
geweckt.clear()
wachen.nach_zug("t-ohne-wache", "Fertig.")
pruefe(not geweckt, "niemand wird geweckt")

print("Eine beendete Wache auch nicht")
wachen.beenden(w["id"], "Ziel erreicht")
geweckt.clear()
wachen.nach_zug("t-abc", "Noch etwas.")
pruefe(not geweckt, "nach dem Ende ist Ruhe")
pruefe(wachen.fuer_sitzung("t-abc") is None, "und sie zaehlt nicht mehr als laufend")

shutil.rmtree(wachen.DIR, ignore_errors=True)

print()
print(f"{ok_count} ok, {len(fehler)} fehlgeschlagen")
sys.exit(1 if fehler else 0)
