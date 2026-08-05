"""Runtime configuration, all overridable through environment variables."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CHORDSMITH_DATA_DIR", BASE_DIR / "data"))
AUDIO_DIR = DATA_DIR / "audio"
DATABASE_PATH = Path(os.environ.get("CHORDSMITH_DB", DATA_DIR / "chordsmith.db"))

# libsndfile decodes these without an external ffmpeg install.
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".oga", ".aiff", ".aif", ".m4a"}
NATIVE_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".oga", ".aiff", ".aif"}

MAX_UPLOAD_BYTES = int(os.environ.get("CHORDSMITH_MAX_UPLOAD_MB", "60")) * 1024 * 1024

# Analysis is CPU-bound; keep a small pool so a burst of uploads cannot starve
# the request handlers.
ANALYSIS_WORKERS = int(os.environ.get("CHORDSMITH_ANALYSIS_WORKERS", "2"))

CORS_ORIGINS = os.environ.get(
    "CHORDSMITH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")


def ensure_directories() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
