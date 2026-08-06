"""Browsing an audio library that already lives on the server.

Uploading a file through a browser to a machine that is already holding that
exact file is silly, and on a NAS it is also slow: the bytes leave the array,
cross the network to a laptop, and come back. This walks the share directly.

Every path that arrives from a client is resolved and checked to be inside the
configured root before anything opens it. That check is the whole security
model of this module, so it is written once, here, and every entry point goes
through it — a request for ``../../../etc/passwd`` has to fail, and so does a
symlink inside the share that points outside it.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import ALLOWED_EXTENSIONS, LIBRARY_ROOT

# Directories that are never worth showing to someone looking for music.
HIDDEN = {"@eaDir", "lost+found", ".Trash-0", "#recycle", ".DS_Store"}


logger = logging.getLogger(__name__)


class LibraryError(Exception):
    """A request that names something outside the library, or nothing at all."""


@dataclass
class Entry:
    name: str
    path: str
    is_dir: bool
    bytes: int

    def to_dict(self) -> dict:
        return {"name": self.name, "path": self.path, "isDir": self.is_dir, "bytes": self.bytes}


def enabled() -> bool:
    return LIBRARY_ROOT is not None and LIBRARY_ROOT.is_dir()


def resolve(relative: str) -> Path:
    """Turn a client-supplied relative path into a real one inside the root.

    ``resolve()`` before the comparison rather than after: it is what collapses
    ``..`` and follows symlinks, so a link inside the share pointing at /etc is
    caught by the same check that catches a traversal written out longhand.
    """
    if not enabled():
        raise LibraryError("No server library is configured")

    root = LIBRARY_ROOT.resolve()
    candidate = (root / relative.lstrip("/")).resolve()
    if candidate != root and root not in candidate.parents:
        raise LibraryError("That path is outside the library")
    if not candidate.exists():
        raise LibraryError("That path does not exist")
    return candidate


def relative_to_root(path: Path) -> str:
    return str(path.resolve().relative_to(LIBRARY_ROOT.resolve()))  # type: ignore[union-attr]


def listing(relative: str = "") -> tuple[str, list[Entry]]:
    """Directories and playable files directly inside ``relative``."""
    directory = resolve(relative)
    if not directory.is_dir():
        raise LibraryError("That path is not a folder")

    entries: list[Entry] = []
    with os.scandir(directory) as scan:
        for item in scan:
            if item.name.startswith(".") or item.name in HIDDEN:
                continue
            try:
                if item.is_dir():
                    entries.append(
                        Entry(name=item.name, path=_child(relative, item.name), is_dir=True, bytes=0)
                    )
                elif Path(item.name).suffix.lower() in ALLOWED_EXTENSIONS:
                    entries.append(
                        Entry(
                            name=item.name,
                            path=_child(relative, item.name),
                            is_dir=False,
                            bytes=item.stat().st_size,
                        )
                    )
            except OSError:
                # A file that vanished or cannot be stat'ed mid-scan is simply
                # not listed; one bad entry must not break browsing a folder.
                continue

    entries.sort(key=lambda entry: (not entry.is_dir, entry.name.lower()))
    return relative_to_root(directory) if relative else "", entries


def _child(parent: str, name: str) -> str:
    return f"{parent.rstrip('/')}/{name}" if parent else name


@dataclass
class Track:
    """One playable file in the library, with what its path says about it."""

    name: str
    path: str
    artist: str
    album: str
    bytes: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "artist": self.artist,
            "album": self.album,
            "bytes": self.bytes,
        }


# The index is a list of every playable file under the root. Twelve thousand
# paths is a couple of megabytes and a fraction of a second to search; walking
# the tree instead, on every keystroke, over a network filesystem, is neither.
_index: list[Track] | None = None
_indexed_at = 0.0
_index_lock = threading.Lock()

# Rebuilt after this long. A music library changes when somebody adds an album,
# which is not something that needs noticing within seconds.
INDEX_TTL = 900


def _normalise(text: str) -> str:
    """Lowercase and strip accents, so "vibracao" finds "Vibração".

    Anyone typing a search on a phone is not going to reach for the tilde, and a
    Portuguese library that only answers to perfectly accented queries answers
    to almost nothing.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def build_index(force: bool = False) -> list[Track]:
    """Walk the library once and remember every playable file."""
    global _index, _indexed_at

    with _index_lock:
        fresh = _index is not None and (time.time() - _indexed_at) < INDEX_TTL
        if fresh and not force:
            return _index  # type: ignore[return-value]

        root = LIBRARY_ROOT
        if root is None or not root.is_dir():
            _index, _indexed_at = [], time.time()
            return []

        found: list[Track] = []
        for directory, subdirectories, files in os.walk(root):
            subdirectories[:] = [
                name for name in subdirectories if not name.startswith(".") and name not in HIDDEN
            ]
            here = Path(directory)
            for filename in files:
                if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
                    continue
                path = here / filename
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                relative = path.relative_to(root)
                parts = relative.parts
                # A beets library nests artist/album/track, sometimes under a
                # category. The two directories directly above a file are
                # therefore the album and the artist, whatever sits above them.
                found.append(
                    Track(
                        name=path.stem,
                        path=str(relative).replace("\\", "/"),
                        artist=parts[-3] if len(parts) >= 3 else "",
                        album=parts[-2] if len(parts) >= 2 else "",
                        bytes=size,
                    )
                )

        logger.info("indexed %d tracks under %s", len(found), root)
        _index, _indexed_at = found, time.time()
        return found


def search(query: str, limit: int = 60) -> list[Track]:
    """Tracks whose path contains every word of the query, in any order.

    Every word rather than the whole phrase, because the useful query is
    "marcelo saideira" — an artist and part of a title that never appear next to
    each other in the path.
    """
    terms = [_normalise(term) for term in query.split() if term.strip()]
    if not terms:
        return []

    matches: list[Track] = []
    for track in build_index():
        haystack = _normalise(f"{track.artist} {track.album} {track.name}")
        if all(term in haystack for term in terms):
            matches.append(track)
            if len(matches) >= limit:
                break
    return matches


def index_size() -> int:
    return len(build_index())


def audio_file(relative: str) -> Path:
    """A path inside the library that is safe to import, or an error saying why."""
    path = resolve(relative)
    if path.is_dir():
        raise LibraryError("That is a folder, not an audio file")
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise LibraryError(f"'{path.suffix or 'unknown'}' is not a supported audio format")
    if path.stat().st_size == 0:
        raise LibraryError("That file is empty")
    return path
