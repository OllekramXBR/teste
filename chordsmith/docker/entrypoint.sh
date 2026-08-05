#!/bin/sh
# Run as the UID/GID the host asks for, so files written to the appdata share
# stay owned by the user rather than by root. Unraid passes PUID/PGID as
# environment variables; defaulting to 99:100 matches Unraid's `nobody:users`.
set -eu

PUID="${PUID:-99}"
PGID="${PGID:-100}"
DATA_DIR="${CHORDSMITH_DATA_DIR:-/data}"

mkdir -p "$DATA_DIR" "$NUMBA_CACHE_DIR"

if [ "$(id -u)" = "0" ]; then
    if ! getent group "$PGID" >/dev/null 2>&1; then
        groupadd -g "$PGID" chordsmith 2>/dev/null || addgroup -g "$PGID" chordsmith
    fi
    if ! getent passwd "$PUID" >/dev/null 2>&1; then
        useradd -u "$PUID" -g "$PGID" -M -s /bin/sh chordsmith 2>/dev/null \
            || adduser -u "$PUID" -G chordsmith -H -D chordsmith
    fi
    chown -R "$PUID:$PGID" "$DATA_DIR" "$NUMBA_CACHE_DIR" 2>/dev/null || true
    exec gosu "$PUID:$PGID" "$@"
fi

exec "$@"
