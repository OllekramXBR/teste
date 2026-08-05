"""Chordsmith API — upload a track, get back a beat-aligned chord chart."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import jobs, storage
from .config import CORS_ORIGINS, MAX_UPLOAD_BYTES, NATIVE_EXTENSIONS, ensure_directories
from .routes import songs as songs_routes
from .routes import theory as theory_routes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("chordsmith")

# Serve the built frontend from the same origin when it is present, so the whole
# app can run as a single process in production.
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_directories()
    storage.init_db()
    requeued = jobs.requeue_incomplete()
    if requeued:
        logger.info("requeued %d interrupted analyses", requeued)
    jobs.warm_up()
    yield
    jobs.shutdown()


app = FastAPI(
    title="Chordsmith",
    description="Automatic chord and beat detection for your own audio files.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in CORS_ORIGINS if origin.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"],
)

app.include_router(songs_routes.router)
app.include_router(theory_routes.router)


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    library = storage.list_songs(limit=500)
    return {
        "status": "ok",
        "songs": len(library),
        "analyzing": sum(1 for s in library if s["status"] in ("pending", "analyzing")),
        "storedBytes": songs_routes.audio_dir_size(),
        "maxUploadBytes": MAX_UPLOAD_BYTES,
        "supportedFormats": sorted(NATIVE_EXTENSIONS),
    }


if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> FileResponse:
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
