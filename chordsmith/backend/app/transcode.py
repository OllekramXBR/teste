"""Convert uploads that libsndfile cannot open into ones it can.

The app decodes everything through libsndfile, which does not handle AAC. Rather
than teach the analysis pipeline a second decoder and have two ways for a file
to be read, an .m4a is converted to FLAC once at upload time and every stage
downstream sees an ordinary, lossless, libsndfile-native file.

FLAC rather than WAV because it is lossless either way and roughly half the
size, and the conversion is from a lossy source, so there is nothing further to
lose.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Long enough for a full-length track on a busy box, short enough that a wedged
# process cannot hold an upload open forever.
TRANSCODE_TIMEOUT = 300


class TranscodeError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def to_flac(source: Path) -> Path:
    """Convert ``source`` to FLAC beside itself and remove the original.

    Returns the new path. Raises :class:`TranscodeError` with ffmpeg's own last
    line of output, which is usually the only useful thing it said.
    """
    if not ffmpeg_available():
        raise TranscodeError(
            "ffmpeg is not installed, so this file type cannot be read. "
            "Convert it to MP3, WAV, FLAC or OGG first."
        )

    destination = source.with_suffix(".flac")
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            # Mixing down or resampling here would throw away information the
            # analysis wants; the only job is to change the container.
            "-vn",
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=TRANSCODE_TIMEOUT,
    )

    if result.returncode != 0 or not destination.exists():
        destination.unlink(missing_ok=True)
        detail = (result.stderr or "").strip().splitlines()
        raise TranscodeError(detail[-1] if detail else "ffmpeg could not read this file")

    source.unlink(missing_ok=True)
    logger.info("transcoded %s to FLAC", source.name)
    return destination
