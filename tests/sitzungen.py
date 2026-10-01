"""Was in der Sitzungsliste und im Verlauf NICHT auftauchen soll.

    python3 -m tests.sitzungen

Zwei Filter, beide am 23.09. aus echten Daten entstanden:

  - Ein Agent aus `/fork` bekommt eine eigene Claude-Sitzungskennung, und
    seine Hooks kommen damit an. Ohne Riegel machte iris daraus eine eigene
    Sitzung - mit dem geerbten Titel, weil der Agent das ganze Gespraech
    kennt. Vier Eintraege standen so fuer eine Sache, drei davon Geister
    ohne laufenden Prozess.

  - Claude Codes fluechtige Taetigkeitszeile ("Reading 1 file, running 1
    shell command…") wurde vom Bildschirm als Nachricht uebernommen und
    blieb stehen, mit Sternchen und "Antwort kopieren", als haette Claude
    das gesagt.

Beide Filter muessen eng sein: was sie zu viel wegwerfen, fehlt hinterher.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.terminals import _ist_fork, _ist_taetigkeit

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


def transkript(*zeilen):
    fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    fh.write("\n".join(zeilen) + "\n")
    fh.close()
    return fh.name


print("Ein Agent aus /fork")
# So sieht die erste Zeile eines geforkten Transkripts wirklich aus.
fork = transkript(
    '{"type":"history-suppression","sessionId":"3f431639","cause":"fork_inherit","ts":"2026-09-23T09:49:56.672Z"}',
    '{"type":"ai-title","aiTitle":"RTSP-Bildlaufzeit und Posenzuordnung"}')
pruefe(_ist_fork(fork), "wird erkannt")

print("Eine gewoehnliche Sitzung")
echt = transkript(
    '{"type":"summary","summary":"Modellauswahl"}',
    '{"type":"user","message":{"role":"user","content":"moin"}}')
pruefe(not _ist_fork(echt), "wird nicht faelschlich erkannt")

print("Die Marke steht weiter unten")
# Nur die ersten Zeilen werden gelesen - taucht fork_inherit spaeter im
# Gespraech als Text auf, zaehlt das nicht.
spaet = transkript(*(['{"type":"user","message":{"content":"hallo"}}'] * 8
                     + ['{"type":"user","message":{"content":"history-suppression fork_inherit"}}']))
pruefe(not _ist_fork(spaet), "zaehlt nicht als Fork")

print("Ohne Transkript")
pruefe(not _ist_fork(""), "leerer Pfad")
pruefe(not _ist_fork("/tmp/gibtsnicht-12345.jsonl"), "Datei fehlt")

for p in (fork, echt, spaet):
    os.unlink(p)

print("Die fluechtige Taetigkeitszeile")
for text in ["Running 1 shell command · 2s...",
             "Reading 1 file, running 1 shell command...",
             "Running 1 shell command…",
             "Analyzing the data…",
             "✻ Searching 3 files…"]:
    pruefe(_ist_taetigkeit(text), f"{text[:40]!r}")

print("Was eine Antwort ist und bleiben muss")
for text in ["Frisch gerendert, aktueller Kamerablick.",
             "Running the numbers gave 4,2 mm — das passt.",
             "Reading 1 file, running 1 shell command…\nUnd dann das Ergebnis.",
             "Die Messung läuft…",
             ""]:
    pruefe(not _ist_taetigkeit(text), f"{text[:40]!r}")

print()
print(f"{ok_count} ok, {len(fehler)} fehlgeschlagen")
sys.exit(1 if fehler else 0)
