"""Browsing the audio already on the server."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import library

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("")
def browse(path: str = Query("", max_length=1024)) -> dict:
    """Folders and playable files inside ``path``, relative to the library root.

    Returns ``enabled: false`` rather than an error when no library is mounted,
    so the interface can simply not offer the feature instead of showing a
    failure for something the user never asked for.
    """
    if not library.enabled():
        return {"enabled": False, "path": "", "entries": []}

    try:
        current, entries = library.listing(path)
    except library.LibraryError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "enabled": True,
        "path": current,
        "parent": _parent(current),
        "entries": [entry.to_dict() for entry in entries],
    }


def _parent(path: str) -> str | None:
    """The folder above ``path``, or ``None`` at the root."""
    if not path:
        return None
    head, _, _ = path.rstrip("/").rpartition("/")
    return head
