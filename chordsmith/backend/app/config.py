"""Runtime configuration, all overridable through environment variables."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CHORDSMITH_DATA_DIR", BASE_DIR / "data"))
AUDIO_DIR = DATA_DIR / "audio"
DATABASE_PATH = Path(os.environ.get("CHORDSMITH_DB", DATA_DIR / "chordsmith.db"))

# libsndfile decodes the native set on its own; the rest go through ffmpeg,
# which is in the image now that source separation needs it anyway.
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".oga", ".aiff", ".aif", ".m4a", ".aac"}
NATIVE_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".oga", ".aiff", ".aif"}

MAX_UPLOAD_BYTES = int(os.environ.get("CHORDSMITH_MAX_UPLOAD_MB", "60")) * 1024 * 1024

# A folder of existing music on the server, mounted read-only, browsable from
# the app. Unset means the feature is simply off — nothing is exposed by
# default, and what is exposed is whatever a human chose to mount at /library.
# The size limit above does not apply here: it exists to bound what a browser
# may push over the network, and these bytes never cross it.
_library = os.environ.get("CHORDSMITH_LIBRARY_ROOT", "/library")
LIBRARY_ROOT = Path(_library) if _library else None

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

# Source separation. Stems are large — four Ogg files per song, roughly the
# size of the original each — so they live beside the audio rather than in the
# database, and can be deleted without losing the analysis.
STEMS_DIR = DATA_DIR / "stems"
STEM_MODEL_DIR = Path(os.environ.get("CHORDSMITH_STEM_MODEL_DIR", DATA_DIR / "models" / "stems"))

# The separator runs in its own virtualenv, as a subprocess. It cannot be
# imported here: its dependencies fight numba over the OpenMP runtime and take
# the analysis pipeline down with them. See the Dockerfile.
SEPARATOR_BIN = Path(
    os.environ.get("CHORDSMITH_SEPARATOR_BIN", "/opt/separator/bin/audio-separator")
)
# Two model passes over a whole recording on a CPU. Generous, because the
# alternative to waiting is a killed job three minutes from the end; bounded,
# because a wedged model must not hold a worker thread forever.
SEPARATION_TIMEOUT = int(os.environ.get("CHORDSMITH_SEPARATION_TIMEOUT", "5400"))

# Two model pairs, and the choice between them is a real trade rather than a
# preference. Stage one splits the mix four ways; stage two splits the vocal
# stem it produced into lead and backing, which Demucs cannot do at any size
# because it has no notion of which voice is the lead.
#
# "fast" is the pair measured at about eight minutes for a four-minute track on
# a CPU. "best" swaps in the fine-tuned Demucs, which scores roughly a decibel
# better on vocals for four times the work, and a Roformer karaoke model whose
# published SDR on the lead/backing split is 10.2 against 5.4 — that second
# difference is the one worth paying for when the point is singing over your own
# backing vocals.
STEM_MODELS: dict[str, tuple[str, str]] = {
    "fast": ("htdemucs.yaml", "UVR_MDXNET_KARA_2.onnx"),
    "best": ("htdemucs_ft.yaml", "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"),
}
STEM_QUALITY = os.environ.get("CHORDSMITH_STEM_QUALITY", "best")


def stem_models(quality: str | None = None) -> tuple[str, str]:
    """The (mix-splitter, karaoke-splitter) pair for a quality name."""
    return STEM_MODELS.get(quality or STEM_QUALITY, STEM_MODELS["fast"])

# MP3 keeps five stems small enough to load into the browser at once, which is
# what the stage view does before it will let anyone press play.
STEM_FORMAT = os.environ.get("CHORDSMITH_STEM_FORMAT", "mp3")

# Accounts exist as soon as someone creates one; they are only *enforced* when
# this says so. Default "open" because this app has always run without a login,
# behind a private network, and switching that on by surprise would lock its
# owner out of their own library.
AUTH_MODE = os.environ.get("CHORDSMITH_AUTH", "open").strip().lower()
SESSION_DAYS = int(os.environ.get("CHORDSMITH_SESSION_DAYS", "30"))

CORS_ORIGINS = os.environ.get(
    "CHORDSMITH_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")


def ensure_directories() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    STEMS_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
