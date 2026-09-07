"""Deciding whether two uploads are the same recording.

By content, not by name. The library that started this had one recording filed
under two different names in two different folders, and both were imported —
so a check on titles or filenames would have caught neither.

SHA-256 of the bytes as they arrived, before any transcoding: a conversion is
not guaranteed to be reproducible, so hashing afterwards could give one file two
different answers on two different days.

What this does not catch is the same performance encoded twice at different
bitrates. Those are different bytes and honestly different files; telling them
apart needs an acoustic fingerprint, which is a much larger thing than this.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# Big enough that a large file is a handful of reads, small enough not to hold
# a whole album in memory while hashing it.
CHUNK = 1024 * 1024


def of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
