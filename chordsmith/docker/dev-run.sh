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

stop() {
    docker rm -f "$WEB" "$API" >/dev/null 2>&1 || true
    echo "Stopped $API and $WEB."
}

if [ "${1:-start}" = "stop" ]; then
    stop
    exit 0
fi

mkdir -p "$DATA_DIR"
docker network create "$NETWORK" >/dev/null 2>&1 || true
docker volume create "$MODULES_VOLUME" >/dev/null 2>&1 || true
stop

echo "Building the API image (frontend build skipped — Vite serves the UI)..."
docker build -t chordsmith-dev-api:latest --target backend "$SOURCE_DIR"

echo "Starting $API on $BIND_IP:8000 ..."
docker run -d --name "$API" \
    --network "$NETWORK" --network-alias api \
    -p "$BIND_IP:8000:8000" \
    -v "$SOURCE_DIR/backend:/app/backend" \
    -v "$DATA_DIR:/data" \
    -e PUID="$PUID" -e PGID="$PGID" \
    -e CHORDSMITH_DATA_DIR=/data \
    -e WATCHFILES_FORCE_POLLING=true \
    -e PYTHONDONTWRITEBYTECODE=1 \
    --restart unless-stopped \
    chordsmith-dev-api:latest \
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir /app/backend >/dev/null

echo "Starting $WEB on $BIND_IP:5173 ..."
docker run -d --name "$WEB" \
    --network "$NETWORK" \
    -p "$BIND_IP:5173:5173" \
    -v "$SOURCE_DIR/frontend:/app" \
    -v "$MODULES_VOLUME:/app/node_modules" \
    -w /app \
    -e VITE_API_TARGET=http://api:8000 \
    -e VITE_USE_POLLING=true \
    --restart unless-stopped \
    node:22-alpine \
    sh -c "npm install && npm run dev -- --host 0.0.0.0" >/dev/null

cat <<MESSAGE

Up. The first start pulls node:22-alpine and runs npm install, so give the UI a
minute before it answers.

  UI   http://$BIND_IP:5173
  API  http://$BIND_IP:8000/api/health

  docker logs -f $WEB      follow the frontend
  docker logs -f $API      follow the API
  sh docker/dev-run.sh stop
MESSAGE
