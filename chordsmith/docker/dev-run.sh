#!/bin/sh
# Start the development stack without Docker Compose.
#
# Unraid does not ship the Compose V2 plugin by default — `docker compose` fails
# with "unknown shorthand flag: 'f'" when it is missing. Installing the Docker
# Compose Manager plugin from Community Applications is the tidier fix; this
# script is the equivalent in plain `docker run` for when you would rather not.
#
# Run it from the chordsmith/ directory:
#
#   sh docker/dev-run.sh              # start
#   sh docker/dev-run.sh stop         # stop and remove the containers
#
# Configuration comes from the same .env the compose file uses.
set -eu

SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
NETWORK=chordsmith-dev
API=chordsmith-dev-api
WEB=chordsmith-dev-web
MODULES_VOLUME=chordsmith-web-modules

if [ -f "$SOURCE_DIR/.env" ]; then
    # shellcheck disable=SC1091
    . "$SOURCE_DIR/.env"
fi

BIND_IP="${BIND_IP:-0.0.0.0}"
DATA_DIR="${DATA_DIR:-/mnt/user/appdata/chordsmith/data}"
PUID="${PUID:-99}"
PGID="${PGID:-100}"
# Published ports only. Inside the containers the API is always on 8000 and Vite
# always on 5173, so the proxy target never has to change with these.
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

stop() {
    docker rm -f "$WEB" "$API" >/dev/null 2>&1 || true
    echo "Stopped $API and $WEB."
}

# Docker's own message for a taken port names 0.0.0.0 even when you asked for a
# specific interface, which reads like the script ignored BIND_IP. It did not:
# a listener on 0.0.0.0 already covers every address, so the bind cannot happen.
# Checking first lets us say which port and point at the override.
port_taken() {
    command -v netstat >/dev/null 2>&1 || return 1
    netstat -tln 2>/dev/null | awk '{print $4}' | sed 's/.*://' | grep -qx "$1"
}

check_port() {
    port_taken "$2" || return 0
    holder="$(docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep ":$2->" | cut -d' ' -f1 | tr '\n' ' ')"
    echo "Port $2 ($1) is already in use${holder:+ by: $holder}." >&2
    echo "Pick a free one in $SOURCE_DIR/.env, e.g. $3=8010, then run this again." >&2
    echo "Ports currently listening on this host:" >&2
    netstat -tln 2>/dev/null | awk '{print $4}' | sed 's/.*://' | grep -E '^[0-9]+$' | sort -nu | tr '\n' ' ' >&2
    echo >&2
    exit 1
}

if [ "${1:-start}" = "stop" ]; then
    stop
    exit 0
fi

mkdir -p "$DATA_DIR"
docker network create "$NETWORK" >/dev/null 2>&1 || true
docker volume create "$MODULES_VOLUME" >/dev/null 2>&1 || true
stop

check_port API "$API_PORT" API_PORT
check_port UI "$WEB_PORT" WEB_PORT

echo "Building the API image (frontend build skipped — Vite serves the UI)..."
docker build -t chordsmith-dev-api:latest --target backend "$SOURCE_DIR"

echo "Starting $API on $BIND_IP:$API_PORT ..."
docker run -d --name "$API" \
    --network "$NETWORK" --network-alias api \
    -p "$BIND_IP:$API_PORT:8000" \
    -v "$SOURCE_DIR/backend:/app/backend" \
    -v "$DATA_DIR:/data" \
    -e PUID="$PUID" -e PGID="$PGID" \
    -e CHORDSMITH_DATA_DIR=/data \
    -e WATCHFILES_FORCE_POLLING=true \
    -e PYTHONDONTWRITEBYTECODE=1 \
    --restart unless-stopped \
    chordsmith-dev-api:latest \
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir /app/backend >/dev/null

echo "Starting $WEB on $BIND_IP:$WEB_PORT ..."
docker run -d --name "$WEB" \
    --network "$NETWORK" \
    -p "$BIND_IP:$WEB_PORT:5173" \
    -v "$SOURCE_DIR/frontend:/app" \
    -v "$MODULES_VOLUME:/app/node_modules" \
    -w /app \
    -e VITE_API_TARGET=http://api:8000 \
    -e VITE_USE_POLLING=true \
    --restart unless-stopped \
    node:22-alpine \
    sh -c "npm install && npm run dev -- --host 0.0.0.0 --port 5173" >/dev/null

cat <<MESSAGE

Up. The first start pulls node:22-alpine and runs npm install, so give the UI a
minute before it answers.

  UI   http://$BIND_IP:$WEB_PORT
  API  http://$BIND_IP:$API_PORT/api/health

  docker logs -f $WEB      follow the frontend
  docker logs -f $API      follow the API
  sh docker/dev-run.sh stop
MESSAGE
