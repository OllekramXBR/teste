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


@router.get("/search")
def search(
    q: str = Query("", max_length=200),
    limit: int = Query(60, ge=1, le=200),
) -> dict:
    """Find a track anywhere in the library by artist, album or title.

    Searching rather than browsing because the library is twelve thousand files
    deep in four hundred folders: clicking down to one of them is not a way to
    find anything.
    """
    if not library.enabled():
        return {"enabled": False, "tracks": [], "indexed": 0}
    return {
        "enabled": True,
        "tracks": [track.to_dict() for track in library.search(q, limit)],
        "indexed": library.index_size(),
    }


@router.post("/reindex", status_code=202)
def reindex() -> dict:
    """Re-walk the library, for when an album was added a moment ago."""
    if not library.enabled():
        raise HTTPException(status_code=409, detail="Nenhuma biblioteca montada")
    return {"indexed": len(library.build_index(force=True))}


def _parent(path: str) -> str | None:
    """The folder above ``path``, or ``None`` at the root."""
    if not path:
        return None
    head, _, _ = path.rstrip("/").rpartition("/")
    return head
