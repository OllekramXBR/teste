"""Album art, pulled out of the audio file itself.

A library organised by beets usually carries its cover embedded in the tags, so
there is nothing to fetch from anywhere: the picture is already inside the file
that was imported. ffmpeg is in the image for source separation, and copying an
attached picture out of a container is the cheapest thing it does.

Extracted once and cached, because doing it per request would mean spawning a
process every time a list of songs is drawn.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .config import COVERS_DIR
from .transcode import ffmpeg_available

logger = logging.getLogger(__name__)

# Long enough for a large picture in a large file, short enough that a wedged
# process cannot hold a request open.
TIMEOUT = 30

# A file recording that a song simply has no cover, so the next request does not
# spawn ffmpeg again to rediscover that. Cheaper than a database column for
# something that is only ever true or absent.
MISSING = ".none"


def cover_path(song_id: str) -> Path:
    return COVERS_DIR / f"{song_id}.jpg"


def extract(song_id: str, audio: Path) -> Path | None:
    """The song's embedded cover, extracting it the first time it is asked for."""
    cached = cover_path(song_id)
    if cached.exists():
        return cached
    if (COVERS_DIR / f"{song_id}{MISSING}").exists():
        return None
    if not ffmpeg_available() or not audio.exists():
        return None

    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(audio),
            # Take the first attached picture, drop the audio, and scale it
            # down: this is drawn at forty pixels in a list, and shipping a
            # 1400px album scan to do that is a waste of everyone's bandwidth.
            "-an",
            "-map",
            "0:v:0",
            "-vf",
            "scale=320:-1",
            "-frames:v",
            "1",
            str(cached),
        ],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )

    if result.returncode != 0 or not cached.exists() or cached.stat().st_size == 0:
        cached.unlink(missing_ok=True)
        (COVERS_DIR / f"{song_id}{MISSING}").write_text("", encoding="utf-8")
        return None

    logger.info("extracted cover for %s (%d bytes)", song_id, cached.stat().st_size)
    return cached


def forget(song_id: str) -> None:
    cover_path(song_id).unlink(missing_ok=True)
    (COVERS_DIR / f"{song_id}{MISSING}").unlink(missing_ok=True)
