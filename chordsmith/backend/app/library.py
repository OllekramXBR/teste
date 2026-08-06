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

import os
from dataclasses import dataclass
from pathlib import Path

from .config import ALLOWED_EXTENSIONS, LIBRARY_ROOT

# Directories that are never worth showing to someone looking for music.
HIDDEN = {"@eaDir", "lost+found", ".Trash-0", "#recycle", ".DS_Store"}


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
