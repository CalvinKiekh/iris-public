#!/bin/sh
# iris heartbeat for shell scripts, cron jobs and systemd units.
# POSIX sh, needs only curl. Same contract as the Python client.
#
#   iris-heartbeat.sh <name> [status] [key=value ...]
#
#   IRIS_URL, IRIS_TOKEN, IRIS_HOST come from the environment.
#
# In a cron job:
#   0 3 * * *  /path/backup.sh && iris-heartbeat.sh nightly-backup ok \
#              || iris-heartbeat.sh nightly-backup error
set -eu

name="${1:?Name fehlt}"
status="${2:-ok}"
shift 2 2>/dev/null || shift 1 2>/dev/null || true

url="${IRIS_URL:-}"
if [ -z "$url" ]; then
  echo "iris-heartbeat: IRIS_URL fehlt - Adresse und Token liefert make ingest-token" >&2
  exit 1
fi
token="${IRIS_TOKEN:-}"
host="${IRIS_HOST:-$(hostname -s 2>/dev/null || hostname)}"
interval="${IRIS_INTERVAL:-60}"

# Remaining key=value pairs become the detail object.
detail="{}"
if [ "$#" -gt 0 ]; then
  detail=""
  for kv in "$@"; do
    k=${kv%%=*}; v=${kv#*=}
    case "$v" in
      ''|*[!0-9.]*) v="\"$v\"" ;;     # quote anything that is not a number
    esac
    detail="${detail:+$detail,}\"$k\":$v"
  done
  detail="{$detail}"
fi

curl -fsS --max-time 10 -X POST "$url/api/heartbeat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $token" \
  -d "{\"name\":\"$name\",\"host\":\"$host\",\"status\":\"$status\",\
\"interval\":$interval,\"detail\":$detail}" >/dev/null
