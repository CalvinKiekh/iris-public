#!/bin/sh
# iris auf einen Container-Wirt bringen (gebaut fuer einen Raspberry Pi mit
# Home Assistant OS) - als eigener Container, neben dem, was dort sonst
# laeuft, aber in nichts damit verbunden. Das Ziel steht in rechner.env.
#
#   tools/pi-ausrollen.sh            aus GitHub ausrollen und neu starten
#   tools/pi-ausrollen.sh --vom-mac  stattdessen den Stand hier kopieren
#   tools/pi-ausrollen.sh --bauen    zusaetzlich das Bild neu bauen
#
# Ausgerollt wird aus dem Klon auf dem Pi, nicht vom Mac. Sonst laeuft dort
# etwas, das es nirgends sonst gibt: bis zum 28.09. kopierte dieses Skript
# den Arbeitsstand des Macs hinueber, waehrend der Klon auf dem Pi 43 Commits
# zurueckhing und niemand ihn benutzte. Was lief, war damit an einen Rechner
# gebunden, der oft aus ist.
#
# `--vom-mac` bleibt fuer den kurzen Versuch, den man nicht erst committen
# will. Er sagt es dann auch deutlich, damit niemand glaubt, das Ausgerollte
# stuende in `main`.
#
# Zwei Eigenheiten des Pi, die den Weg bestimmen:
#
#   - Kein `docker compose`. Portainer bringt seine eigene Compose-Maschine
#     mit, von aussen ist sie nicht zu haben. Deshalb `docker` von Hand; die
#     compose-Datei liegt trotzdem daneben, damit der Stack spaeter in
#     Portainer uebernommen werden kann, ohne dass jemand ihn neu erfindet.
#   - Kein rsync. Also tar durch die SSH-Leitung.
#
# Die Projekte des Pi werden einzeln eingehaengt, nicht der ganze
# share-Ordner. Der enthaelt naemlich auch `authorized_keys` - und eine
# Sitzung, die sich dort selbst eintragen koennte, haette sich damit SSH auf
# den Wirt verschafft. Wer beaufsichtigt, darf beauftragen, aber sich nicht
# selbst mehr Zugang geben; das gilt auch fuer eine Sitzung, die nur helfen
# will. Neue Projekte kommen als eigene Zeile dazu.
#
# Kein Tailscale-Sidecar: der Pi haengt schon im Tailnet. Ein Sidecar haette
# nur einen zweiten Geraetenamen gebracht und dafuer einen Auth-Key verlangt,
# den jemand erzeugen und erneuern muss. (Worauf die Bruecke horcht, steht
# weiter unten - nicht auf der Tailnet-Adresse, das geht auf diesem Pi
# nicht.)
set -e
cd "$(dirname "$0")/.."

. tools/rechner.sh
brauche IRIS_PI_HOST "der SSH-Name des Container-Wirts"
PI="$IRIS_PI_HOST"
ZIEL="${IRIS_PI_PFAD:-/mnt/data/supervisor/share/iris}"
# Weitere Ordner des Wirts fuer die Sitzungen dort, als -v wirt:container.
# Aus rechner.env, nicht fest hier: welche Projekte ein Wirt hat, ist Sache
# dessen, dem er gehoert.
EINHAENGEN=""
for paar in ${IRIS_PI_PROJEKTE:-}; do EINHAENGEN="$EINHAENGEN -v $paar"; done
KLON="${IRIS_PI_KLON:-$ZIEL/arbeit/projekte/iris}"
UID_IM_BILD=1001
QUELLE=git
for a in "$@"; do [ "$a" = "--vom-mac" ] && QUELLE=mac; done

for ordner in bridge web sim hooks; do
  [ -d "$ordner" ] || { echo "$ordner/ fehlt hier - abgebrochen"; exit 1; }
done
[ -f run_bridge.py ] || { echo "run_bridge.py fehlt hier - abgebrochen"; exit 1; }

ssh "$PI" "mkdir -p $ZIEL/code $ZIEL/arbeit"
# Erst leeren, dann fuellen: sonst bleibt auf dem Pi Code liegen, den es
# in der Quelle laengst nicht mehr gibt, und niemand merkt es.
ssh "$PI" "rm -rf $ZIEL/code/bridge $ZIEL/code/web $ZIEL/code/sim $ZIEL/code/hooks"

if [ "$QUELLE" = git ]; then
  # Sagen, was hier noch nicht in main steht - sonst rollt man aus und
  # wundert sich, dass die eigene Aenderung fehlt.
  OFFEN=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
  VORAUS=$(git rev-list --count '@{upstream}..HEAD' 2>/dev/null || echo 0)
  [ "$OFFEN" != 0 ] && echo "  Hinweis: $OFFEN Datei(en) hier nicht eingecheckt - sie gehen NICHT mit."
  [ "$VORAUS" != 0 ] && echo "  Hinweis: $VORAUS Commit(s) nicht gepusht - sie gehen NICHT mit."
  echo "hole main auf $PI ..."
  ssh "$PI" "docker exec -i iris-bridge sh -c 'cd /arbeit/projekte/iris && git fetch --quiet origin && git pull --ff-only --quiet origin main && git log -1 --format=\"  Stand: %h %ad %s\" --date=short'"
  ssh "$PI" "cd $KLON && tar cf - --exclude '__pycache__' bridge web sim hooks run_bridge.py | tar xf - -C $ZIEL/code"
  echo "  aus dem Klon auf dem Pi"
else
  echo "kopiere den Arbeitsstand dieses Macs nach $PI:$ZIEL/code ..."
  echo "  ACHTUNG: das ist NICHT, was in main steht."
  tar czf - --exclude '__pycache__' --exclude '.DS_Store' \
      bridge web sim hooks run_bridge.py \
    | ssh "$PI" "tar xzf - -C $ZIEL/code"
  echo "  $(find bridge web sim hooks -type f ! -path '*__pycache__*' | wc -l | tr -d ' ') Dateien"
fi

tar czf - -C pi Dockerfile docker-compose.yml | ssh "$PI" "tar xzf - -C $ZIEL"
ssh "$PI" "chown -R $UID_IM_BILD:$UID_IM_BILD $ZIEL/arbeit"

if [ "$1" = "--bauen" ]; then
  echo "baue das Bild (beim ersten Mal dauert es, npm holt Claude Code) ..."
  # Ein zweites GitHub-Konto (rechner.env) geht als Build-Argument ins Bild.
  ssh "$PI" "cd $ZIEL && docker build --build-arg GITHUB_ARBEIT=${IRIS_GITHUB_ARBEIT:-} -t iris-bridge:local ."
fi
ssh "$PI" "docker image inspect iris-bridge:local >/dev/null 2>&1" || {
  echo "Das Bild iris-bridge:local gibt es nicht - einmal mit --bauen starten."
  exit 1
}

echo "starte die Bruecke neu ..."
# Worauf die Bruecke horcht: alle Adressen. Am Mac bindet sie nur die
# Tailnet-Adresse (bridge/server.py), auf diesem Pi kann sie das nicht.
#
# Der Grund steht in der nat-Tabelle des Wirts, in PREROUTING und OUTPUT:
#
#   DNAT  all  --  0.0.0.0/0  <Tailnet-Adresse>  ->  <LAN-Adresse>
#
# Alles an die Tailnet-Adresse wird auf die LAN-Adresse umgeschrieben, bevor
# der Kernel den Socket sucht. Ein Socket, der ausdruecklich die Tailnet-Adresse
# bindet, bekommt darum nie ein Paket: das bind gelingt, /proc/net/tcp zeigt
# ihn als LISTEN, und jede Verbindung wird abgewiesen - auch die von diesem
# Rechner auf sich selbst. Nachgemessen am 27.09. mit einem blanken Socket,
# damit klar war, dass es nicht iris ist. Home Assistant (8123) und der
# Feuchtetest (8095) sind erreichbar, weil sie 0.0.0.0 binden.
#
# Loopback allein genuegte fuer die Bruecke, solange das Tailscale-Add-on im
# Userspace-Modus lief - das reichte eingehenden Verkehr nach localhost
# weiter. Seit dem Kernmodus (`userspace_networking: false`, 27.09., damit
# der Pi auch *hinaus* kommt) gibt es diesen Umweg nicht mehr.
#
# Was das kostet, offen gesagt: die Bruecke haengt damit auch im Heim-LAN,
# nicht nur im Tailnet. Ihr Schutz ist dann allein das Token im Kopf jeder
# Anfrage - dasselbe, was Home Assistant auf derselben Maschine tut. So
# entschieden von Calvin am 27.09., nachdem beides auf dem Tisch lag: er hat
# den Befehl selbst gesetzt. Dafuer haengt die Erreichbarkeit nicht an einer
# DNAT-Regel, die niemand von uns gesetzt hat.
# Der Token steht in der .env auf dem Pi und kommt nie durch diese Datei.
ssh "$PI" "
  set -e
  cd $ZIEL
  . ./.env
  HORCHT=0.0.0.0
  ip -o -4 addr show tailscale0 >/dev/null 2>&1 \\
    || echo 'Kein tailscale0 - siehe userspace_networking im Tailscale-Add-on.' >&2
  echo \"  horcht auf \$HORCHT:8780\"
  docker rm -f iris-bridge >/dev/null 2>&1 || true
  docker run -d --name iris-bridge --restart unless-stopped \
    --network host \
    --user $UID_IM_BILD:$UID_IM_BILD \
    -e HOME=/arbeit \
    -e CLAUDE_CODE_OAUTH_TOKEN=\"\$CLAUDE_CODE_OAUTH_TOKEN\" \
    -v $ZIEL/code:/opt/iris:ro \
    -v $ZIEL/arbeit:/arbeit \
    $EINHAENGEN \
    -w /opt/iris \
    iris-bridge:local \
    python3 -m bridge --host \"\$HORCHT\" --port 8780 >/dev/null
"
sleep 4
ssh "$PI" "docker ps --filter name=iris- --format '  {{.Names}}  {{.Status}}'"
echo
echo "Logbuch:  ssh $PI 'docker logs -f iris-bridge'"
echo "Token:    ssh $PI 'docker exec iris-bridge cat /arbeit/.config/iris/config.json'"
