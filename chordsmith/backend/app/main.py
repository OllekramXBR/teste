"""Metatron API — upload a track, get back a beat-aligned chord chart."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import jobs, storage
from .config import (
    ALLOWED_EXTENSIONS,
    CORS_ORIGINS,
    MAX_UPLOAD_BYTES,
    ensure_directories,
)
from . import auth
from .routes import auth as auth_routes
from .routes import cifraclub as cifraclub_routes
from .routes import library as library_routes
from .routes import mp3pm as mp3pm_routes
from .routes import setlists as setlist_routes
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
    auth.init()

    # Anything made before accounts existed belongs to whoever set the server
    # up, which is the first account. Left ownerless it has no owner for the
    # rules to compare against — and the last time that was papered over by
    # showing ownerless things to everyone, one person's set list appeared in
    # another person's account.
    owner = storage.first_user_id()
    if owner:
        songs, setlists = storage.adopt_orphans(owner)
        if songs or setlists:
            logger.info("claimed %d songs and %d setlists for the first account", songs, setlists)
    requeued = jobs.requeue_incomplete()
    if requeued:
        logger.info("requeued %d interrupted analyses", requeued)
    swept = jobs.sweep_untreated_library()
    if swept["lyrics"] or swept["stems"]:
        logger.info(
            "startup sweep queued %d lyrics and %d separations",
            swept["lyrics"],
            swept["stems"],
        )
    jobs.start_library_sweep_loop()
    jobs.warm_up()
    yield
    jobs.shutdown()


app = FastAPI(
    title="Metatron",
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

# Reachable without a session, and each one for a stated reason. Everything
# else — every song, every stem, every byte of audio — is refused.
PUBLIC_PREFIXES = ("/api/auth/",)
PUBLIC_PATHS = frozenset({"/api/health"})

# Not under /api/, and therefore missed by a prefix check: the interactive docs
# and the schema describe every endpoint this server has. That is a map of the
# building handed to someone who has not been let in.
PRIVATE_WHEN_CLOSED = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def require_session(request, call_next):
    """Refuse anything but the sign-in door when accounts are enforced.

    A middleware rather than a per-route dependency, so a route added later
    cannot forget it. Health stays open because a monitor has to reach it, and
    the auth endpoints stay open because a sign-in form has to reach them —
    including registration, which is what stops enabling this before anybody has
    an account from locking the owner out of their own library.
    """
    if not auth.enabled():
        return await call_next(request)

    path = request.url.path
    guarded = path.startswith("/api/") or path.startswith(PRIVATE_WHEN_CLOSED)
    exempt = path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)

    if guarded and not exempt:
        if auth.user_for_token(request.cookies.get(auth.SESSION_COOKIE)) is None:
            return JSONResponse({"detail": "Entre para continuar"}, status_code=401)
    return await call_next(request)


app.include_router(auth_routes.router)
app.include_router(cifraclub_routes.router)
app.include_router(cifraclub_routes.song_router)
app.include_router(library_routes.router)
app.include_router(mp3pm_routes.router)
app.include_router(setlist_routes.router)
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
        # Everything the upload endpoint accepts, not only what libsndfile
        # opens directly: .m4a has been converted at the door since ffmpeg
        # arrived, and reporting the shorter list told clients to reject
        # files this server handles fine.
        "supportedFormats": sorted(ALLOWED_EXTENSIONS),
    }


if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> FileResponse:
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
