# syntax=docker/dockerfile:1

# ---- Stage 1: build the frontend ------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install

COPY frontend/ ./
RUN npm run build


# ---- Stage 2: runtime ------------------------------------------------------
FROM python:3.11-slim AS runtime

# libsndfile is what actually decodes MP3/FLAC/OGG. The soundfile wheel bundles
# a copy, but installing the system package keeps things working if a future
# wheel stops doing so. gosu drops privileges to the PUID/PGID Unraid passes in.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 gosu curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    CHORDSMITH_DATA_DIR=/data \
    NUMBA_CACHE_DIR=/tmp/numba

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/backend"]
