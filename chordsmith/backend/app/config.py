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

# Lyric transcription. The model is downloaded on first use into the data
# volume, so a rebuilt container does not fetch it again — which also means the
# size chosen here is a disk cost as well as a CPU one:
#
#   small   ~0.5 GB on disk, the default: usable Portuguese, several times
#           faster than real time on a modern CPU
#   medium  ~1.5 GB, noticeably better on sung words, roughly 3x slower
#   large-v3 ~3 GB, only worth it if the box has cores to spare
ASR_MODEL = os.environ.get("CHORDSMITH_ASR_MODEL", "small")
ASR_MODEL_DIR = Path(os.environ.get("CHORDSMITH_ASR_MODEL_DIR", DATA_DIR / "models"))
# int8 quantisation is what makes CPU inference practical; float32 is available
# for a box with RAM to burn and a taste for marginal accuracy.
ASR_COMPUTE_TYPE = os.environ.get("CHORDSMITH_ASR_COMPUTE", "int8")
# Fixing the language beats autodetection here: a sung intro in any language
# fools the detector, and this tool is aimed at Portuguese. Empty means detect.
ASR_LANGUAGE = os.environ.get("CHORDSMITH_ASR_LANGUAGE", "pt")
ASR_BEAM_SIZE = int(os.environ.get("CHORDSMITH_ASR_BEAM", "5"))
# 0 lets CTranslate2 pick, which is the core count.
ASR_THREADS = int(os.environ.get("CHORDSMITH_ASR_THREADS", "0"))

CORS_ORIGINS = os.environ.get(
    "CHORDSMITH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")


def ensure_directories() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
