#!/bin/sh
# Die Bruecke auf den PC bringen - VOLLSTAENDIG, und danach nachsehen.
#
#   tools/pc-ausrollen.sh
#
# WARUM ES DIESES SKRIPT GIBT. Am 13.09. fehlte auf dem PC der Ordner `web/`
# ganz. Die Bruecke liefert die Oberflaeche aus ROOT/web; ohne ihn beantwortet
# sie `/` mit 404, und die App laedt auf iPhone und Mac nicht einmal. Die API
# war dabei gesund - jeder /api/-Aufruf gab 200 - also sah alles nach einem
# Fehler in der App aus. Gefunden hat es die PC-Seite nach Stunden, im
# Quervergleich der beiden Bruecken.
#
# Der Grund war einfach: Wer `bridge/` von Hand kopiert, vergisst `web/`.
# Darum kopiert dieses Skript ALLES, was die Bruecke braucht, startet sie neu
# und BELEGT danach, dass die Oberflaeche steht. Ein Ausrollen, das man
# glauben muss, ist keins.
set -e
cd "$(dirname "$0")/.."
. tools/rechner.sh
brauche IRIS_PC "der SSH-Name des Windows-PCs"
brauche IRIS_PC_URL "die Adresse seiner Bruecke, z. B. http://100.x.y.z:8780"
PC="$IRIS_PC"
ZIEL="${IRIS_PC_PFAD:-iris}"
ADRESSE="$IRIS_PC_URL"

echo "kopiere nach $PC:$ZIEL ..."
# bridge allein reicht nicht: web/ und sim/ sind die Oberflaeche (ohne sie
# antwortet / mit 404), hooks/ ist das, worauf die settings.json auf dem PC
# zeigt. Was hier fehlt, driftet auseinander, ohne dass es jemand merkt.
for ordner in bridge web sim hooks; do
  [ -d "$ordner" ] || { echo "  $ordner/ fehlt hier - abgebrochen"; exit 1; }
  ssh "$PC" "New-Item -ItemType Directory -Force -Path $ZIEL\\$ordner | Out-Null" >/dev/null
  scp -q -r "$ordner"/* "$PC:$ZIEL/$ordner/"
  echo "  $ordner/ ($(find "$ordner" -type f | wc -l | tr -d ' ') Dateien)"
done
# Der Starter waelzt das Log um - er gehoert dazu, nicht auf den PC allein.
[ -f run_bridge.py ] || { echo "  run_bridge.py fehlt hier - abgebrochen"; exit 1; }
scp -q run_bridge.py "$PC:$ZIEL/"

echo "starte die Bruecke neu ..."
ssh "$PC" "@(Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | Where-Object {\$_.CommandLine -like '*run_bridge*'}) | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }; Start-Sleep -Seconds 3; Start-ScheduledTask -TaskName 'iris Bruecke'" >/dev/null
sleep 10

# Der Beleg. Nicht die Datei zaehlt, sondern die Antwort.
TOKEN=$(ssh "$PC" "(Get-Content -Raw \$env:USERPROFILE\\.config\\iris\\config.json | ConvertFrom-Json).token" | tr -d '\r\n')
OBERFLAECHE=$(curl -s -o /dev/null -m 15 -w "%{http_code}" "$ADRESSE/?token=$TOKEN")
API=$(curl -s -o /dev/null -m 15 -w "%{http_code}" "$ADRESSE/api/health?token=$TOKEN")
echo "Oberflaeche /      -> $OBERFLAECHE"
echo "API /api/health    -> $API"
[ "$OBERFLAECHE" = "200" ] || { echo "FEHLER: Die Oberflaeche kommt nicht - so laedt die App nicht."; exit 1; }
[ "$API" = "200" ] || { echo "FEHLER: Die API antwortet nicht."; exit 1; }
echo "steht."
