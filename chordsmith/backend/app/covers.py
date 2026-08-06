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


# Words that mark a file as the front cover, in the languages this library is
# actually filed in. Checked before falling back to "the biggest picture".
COVER_WORDS = ("cover", "folder", "front", "capa", "albumart", "-f.")

# And words that mark one as definitely not: a back cover or a label's logo is
# the wrong picture, and on this library it is often also the largest.
NOT_COVER_WORDS = ("back", "-b.", "logo", "cd", "disc", "inlay", "booklet")

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def pick_folder_image(folder: Path) -> Path | None:
    """The most likely front cover sitting beside an album's tracks.

    Not every library embeds art — this one does not — but almost every one
    keeps a picture in the album folder. The names are not standardised, so
    they are scored: a filename that says it is the cover wins, a filename that
    says it is the back or a logo is excluded outright, and what survives is
    ranked by size on the theory that the front scan is the big one.
    """
    if not folder.is_dir():
        return None

    candidates: list[tuple[int, int, Path]] = []
    try:
        entries = list(folder.iterdir())
    except OSError:
        return None

    for path in entries:
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        name = path.name.lower()
        if any(word in name for word in NOT_COVER_WORDS):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        named = 1 if any(word in name for word in COVER_WORDS) else 0
        candidates.append((named, size, path))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def from_folder(song_id: str, folder: Path) -> Path | None:
    """Copy an album folder's cover in as this song's, scaled down.

    Falls back to the artist folder above it. Plenty of libraries keep one
    picture per artist rather than one per album, and an artist photo on the
    right song beats a grey square — while looking further up than that would
    start putting a genre's picture on everything inside it.
    """
    source = pick_folder_image(folder) or pick_folder_image(folder.parent)
    if source is None or not ffmpeg_available():
        return None

    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    target = cover_path(song_id)
    result = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-vf", "scale=320:-1", "-frames:v", "1", str(target),
        ],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
        target.unlink(missing_ok=True)
        return None

    (COVERS_DIR / f"{song_id}{MISSING}").unlink(missing_ok=True)
    logger.info("took cover for %s from %s", song_id, source.name)
    return target


def forget(song_id: str) -> None:
    cover_path(song_id).unlink(missing_ok=True)
    (COVERS_DIR / f"{song_id}{MISSING}").unlink(missing_ok=True)
