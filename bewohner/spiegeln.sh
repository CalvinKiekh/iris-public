#!/bin/sh
# Mirrors the resident's code and notes from the PC into this repo, so every
# state on the PC is versioned here too. The PC is the source; nothing goes
# back this way (gespraech.py, which the Mac owns, is deployed with deploy).
# Never mirrored: the workspace (werkstatt), recordings, logs, keys.
set -e
cd "$(dirname "$0")/.."
. tools/rechner.sh
brauche IRIS_PC "der SSH-Name des PCs, auf dem der Bewohner laeuft"
PC="$IRIS_PC"
cd bewohner

# SPERRE. Seit dem 28.09.2026 ist das Repo dem PC voraus: Name und Pfade
# kommen hier aus einstellungen.py, auf dem PC stehen sie noch fest im Code.
# Ein Spiegeln in diese Richtung wuerde das stillschweigend zurueckdrehen.
# Also erst nachsehen, ob der PC die neue Fassung schon hat.
PROBE=$(mktemp)
scp -q "$PC:mcp-test/bewohner.py" "$PROBE"
if ! grep -q "^import einstellungen" "$PROBE"; then
  rm -f "$PROBE"
  echo "Abgebrochen: der Code auf $PC ist noch die Fassung ohne einstellungen.py." >&2
  echo "Spiegeln wuerde den Umbau im Repo rueckgaengig machen. Erst die Fassung" >&2
  echo "aus dem Repo auf den PC bringen, dann wieder spiegeln." >&2
  exit 1
fi
rm -f "$PROBE"
scp -q "$PC:mcp-test/*.py" .
scp -q "$PC:tts-test/sprich.py" "$PC:tts-test/normalisieren.py" .
scp -q "$PC:mcp-test/werkstatt/regeln.json" . 2>/dev/null || true
# What he wrote about himself belongs in the history too - the capability
# list, the tools, his own notes. Not lage.json: that changes every 30 s.
for f in faehigkeiten.json werkzeuge.json ICH.md WUENSCHE.md; do
    scp -q "$PC:mcp-test/werkstatt/$f" selbst/ 2>/dev/null || true
done
# The ten tools he wrote himself. They live under werkstatt/, which the PC
# repo ignores wholesale - so without this they exist in exactly one place.
scp -q "$PC:mcp-test/werkstatt/werkzeuge/*.py" werkzeuge/ 2>/dev/null || true

# What he has learned, and what he is due to be reminded of. On 12.09. at
# about 21:00 a test's cleanup pointed at the real workshop and deleted it:
# 131 memories, the core knowledge, the appointments, the whole journal. The
# self-image and the tools above came back from here; these three did not,
# because nobody had thought to take them along. werkstatt/ is in the PC's
# .gitignore, so this mirror is the only backup that exists.
#
# The database first: SQLite writes in place, so a copy taken mid-write can
# arrive half-finished. sqlite3 on the PC makes a consistent one; if it is
# not there, the plain copy is still better than nothing - it is a fallback,
# not the plan.
# sicherung/ ist seit dem 29.09.2026 nicht mehr im Git (.gitignore): das
# Gedaechtnis gehoert nicht in ein Repo, das gepusht und weitergegeben wird.
# Die Sicherung bleibt - sie liegt nur noch auf diesem Rechner. Was darin
# steht und wie man zurueckspielt: bewohner/GEDAECHTNIS.md.
mkdir -p sicherung
ssh "$PC" "sqlite3 \$env:USERPROFILE\\mcp-test\\werkstatt\\gedaechtnis.db \".backup '\$env:USERPROFILE\\mcp-test\\werkstatt\\_sicher.db'\"" >/dev/null 2>&1 \
  && scp -q "$PC:mcp-test/werkstatt/_sicher.db" sicherung/gedaechtnis.db 2>/dev/null \
  || scp -q "$PC:mcp-test/werkstatt/gedaechtnis.db" sicherung/gedaechtnis.db 2>/dev/null || true
ssh "$PC" 'Remove-Item -Force "$env:USERPROFILE\mcp-test\werkstatt\_sicher.db" -ErrorAction SilentlyContinue' >/dev/null 2>&1 || true
for f in ERINNERUNG.md erinnerungen.json; do
    scp -q "$PC:mcp-test/werkstatt/$f" sicherung/ 2>/dev/null || true
done

# Der unersetzliche Rest, nach SPIEGELUNG.md des Bewohners: alles, was nach
# einem Verlust nicht wieder herzustellen ist. Zusammen unter 200 KB - kleiner
# als eine einzelne Sprachantwort. Die 8,9 MB mp3 bleiben absichtlich drau"sen:
# der Text steht im Journal, der Ton ist Bequemlichkeit.
#
#   journal.jsonl        die Chronik. Nichts kann sie nachbauen; rueckblick,
#                        passiert und anlaesse lesen ausschliesslich daraus.
#   sitzungen*           der Wortlaut jedes Gespraechs. Eine Zusammenfassung
#                        ohne ihn ist nicht nachpruefbar (D liest ihn).
#   beschreibungen.json  ein Satz je Datei, 165 Modellaufrufe wert.
#   gesehen.json         die Merkliste. Fehlt sie, kostet der naechste Start
#                        165 Aufrufe fuer dasselbe Ergebnis.
#   bestand.json         welche Erkenntnis unter welcher Kennung liegt - ohne
#                        sie wird jeder Fakt neu angelegt statt ueberholt.
#   pruefung.json        welcher Verdacht schon vorgelegt wurde. Fehlt sie,
#                        meldet die Nacht jeden Morgen dasselbe.
#   anlaesse/ansprachen  was er von sich aus schon gesagt hat.
#   platzverlauf/rhythmus/blicke  Messreihen: nur als LANGE Reihe etwas wert,
#                        und nur neu anzufangen, nicht nachzubauen. Sie fehlen
#                        seit dem 12.09.; hier stehen sie, damit sie vom ersten
#                        Tag an mitkommen, sobald sie wieder wachsen.
for f in journal.jsonl sitzungen.jsonl beschreibungen.json gesehen.json \
         bestand.json pruefung.json anlaesse.json ansprachen.jsonl \
         platzverlauf.jsonl rhythmus.json; do
    scp -q "$PC:mcp-test/werkstatt/$f" sicherung/ 2>/dev/null || true
done
mkdir -p sicherung/sitzungen
scp -q "$PC:mcp-test/werkstatt/sitzungen/*.json" sicherung/sitzungen/ 2>/dev/null || true
# aufgabe-einrichten.ps1 kommt nicht mehr mit: das Repo ist dafuer die Quelle
# (bewohner/aufgabe-einrichten.ps1), auf dem PC liegt noch die alte Fassung.
for f in NACHT-PLAN.md PLAN.md IDEEN.md KARTIERUNG.md ZUSTAND-PC.md OFFEN-PC.md 'BERICHT-*.md' 'AUFTRAG-*.md' 'NACHBESSERUNG-*.md'; do
    scp -q "$PC:mcp-test/$f" docs/ 2>/dev/null || true
done
rm -f docs/AUFTRAG-IRIS.md            # a copy of ../docs/BEWOHNER.md
# Nothing secret may come along.
# (this script is left out: it names the patterns it looks for)
if grep -rlE --exclude=spiegeln.sh 'sk_[A-Za-z0-9]{10}|BXZl25|xi-api-key.{0,5}[A-Za-z0-9]{20}' . ; then
    echo "Geheimnis gefunden - nicht committen" >&2
    exit 1
fi
git -C .. status --short -- bewohner | head -40
