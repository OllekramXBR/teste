# syntax=docker/dockerfile:1

# ---- Stage 1: build the frontend ------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install

COPY frontend/ ./
RUN npm run build


# ---- Stage 2: everything the API needs, minus the built frontend -----------
# Split out so development can build this stage alone and skip the frontend
# build entirely — in development Vite serves the UI itself.
FROM python:3.11-slim AS backend

# libsndfile is what actually decodes MP3/FLAC/OGG. The soundfile wheel bundles
# a copy, but installing the system package keeps things working if a future
# wheel stops doing so. gosu drops privileges to the PUID/PGID Unraid passes in.
#
# ffmpeg arrived with source separation, which needs it, and paid for itself
# twice over: it is also what lets the app accept the .m4a/AAC files it used to
# reject, and what encodes the stems as MP3 so four of them can stream at once.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 ffmpeg gosu curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    CHORDSMITH_DATA_DIR=/data \
    NUMBA_CACHE_DIR=/tmp/numba

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# The separation stack gets its own interpreter, and this is not tidiness.
# Installed next to the packages above it drags in torch and scikit-learn, which
# fight numba and librosa over the OpenMP runtime, and the analysis pipeline
# then dies with a segmentation fault — not the separator, the whole pipeline.
# Neither OMP_NUM_THREADS=1 nor KMP_DUPLICATE_LIB_OK=TRUE avoids it.
#
# In its own virtualenv, invoked as a subprocess, none of it is ever loaded into
# the API process. The separator also cannot take the server down by crashing,
# and its memory is returned to the machine when it exits rather than being held
# for the life of the process.
#
# diffq, one of its dependencies, publishes no wheel for this Python, so a
# compiler has to exist while pip runs. It is added and removed inside a single
# layer: in its own RUN it would stay in the image forever, because a later
# layer cannot delete what an earlier one wrote.
ENV SEPARATOR_VENV=/opt/separator
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && python -m venv "$SEPARATOR_VENV" \
    && "$SEPARATOR_VENV/bin/pip" install --no-cache-dir "audio-separator[cpu]>=0.30" \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ ./backend/
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/backend"]


# ---- Stage 3: production image, API plus the built UI ----------------------
FROM backend AS runtime

COPY --from=frontend /build/dist ./frontend/dist
