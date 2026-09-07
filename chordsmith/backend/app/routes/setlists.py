"""Setlists: the running order of a show."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import auth, storage

router = APIRouter(prefix="/api/setlists", tags=["setlists"])


class SetlistCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str = Field("", max_length=2000)


class SetlistUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    notes: str | None = Field(None, max_length=2000)


class SetlistOrder(BaseModel):
    songs: list[str] = Field(max_length=200)


@router.get("")
def list_setlists(request: Request) -> dict:
    return {"setlists": storage.list_setlists(viewer_id=auth.viewer_id(request))}


@router.post("", status_code=201)
def create_setlist(payload: SetlistCreate, request: Request) -> dict:
    return storage.create_setlist(
        payload.name.strip(), payload.notes.strip(), owner_id=auth.current_user_id(request)
    )


@router.get("/{setlist_id}")
def get_setlist(setlist_id: str) -> dict:
    setlist = storage.get_setlist(setlist_id)
    if not setlist:
        raise HTTPException(status_code=404, detail="Setlist not found")
    return setlist


@router.patch("/{setlist_id}")
def update_setlist(setlist_id: str, payload: SetlistUpdate) -> dict:
    name = payload.name.strip() if payload.name is not None else None
    if not storage.update_setlist(setlist_id, name, payload.notes):
        raise HTTPException(status_code=404, detail="Setlist not found")
    return storage.get_setlist(setlist_id)  # type: ignore[return-value]


@router.put("/{setlist_id}/songs")
def set_songs(setlist_id: str, payload: SetlistOrder) -> dict:
    """Replace the running order.

    Duplicates are dropped rather than rejected: the same song twice in one set
    is almost always a double tap, and failing the whole request over it would
    lose the reordering that came with it.
    """
    seen: set[str] = set()
    unique = [song for song in payload.songs if not (song in seen or seen.add(song))]

    if not storage.set_setlist_songs(setlist_id, unique):
        raise HTTPException(status_code=404, detail="Setlist not found")
    return storage.get_setlist(setlist_id)  # type: ignore[return-value]


@router.delete("/{setlist_id}", status_code=204)
def delete_setlist(setlist_id: str) -> Response:
    if not storage.delete_setlist(setlist_id):
        raise HTTPException(status_code=404, detail="Setlist not found")
    return Response(status_code=204)
