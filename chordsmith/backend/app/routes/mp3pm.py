"""Finding a track that mp3.pm has and the server library does not.

The library search answers "is this already here?". This answers "if it is not,
where can I get it, and then analyse it" — search mp3.pm, download the chosen
result into the music folder, and import it through the same path an upload
takes, so the analysis and the stem separation that follow are the ones the app
already knows how to do.
"""

from __future__ import annotations

import shutil
import subprocess

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .. import auth, jobs, mp3pm, storage, transcode
from ..config import AUDIO_DIR, MUSIC_DIR, NATIVE_EXTENSIONS

router = APIRouter(prefix="/api/mp3pm", tags=["mp3pm"])


@router.get("/search")
def search(
    q: str = Query("", max_length=200),
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    """Tracks on mp3.pm that match the query.

    A query that the local library does not contain is the only reason this
    endpoint exists; it is offered by the interface exactly when that happens.
    """
    query = q.strip()
    if not query:
        return {"results": []}
    try:
        results = mp3pm.search(query, limit)
    except mp3pm.Mp3pmError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"results": [track.to_dict() for track in results]}


class ImportRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    sound_id: str = Field(max_length=40)
    title: str = Field("", max_length=200)
    artist: str = Field("", max_length=200)


@router.post("/import", status_code=201)
def import_track(payload: ImportRequest, request: Request) -> dict:
    """Download a searched track, then import it like any other file.

    The search is redone here and the result matched by its id, so the server
    builds every destination it fetches — a client can ask for a song it saw in
    the results, and nothing else. The downloaded MP3 stays in the music folder
    as the permanent copy, and a second copy goes through the normal import
    path (analyse, then separate into stems) against the app's own audio store.
    """
    track = mp3pm.find(payload.query.strip(), payload.sound_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Essa faixa não está mais no mp3.pm")

    try:
        source = mp3pm.download(track)
    except mp3pm.Mp3pmError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    song_id = storage.new_id()
    extension = source.suffix.lower()
    destination = AUDIO_DIR / f"{song_id}{extension}"
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy2(source, destination)
    except OSError as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not store the file: {error}") from error

    if extension not in NATIVE_EXTENSIONS:
        try:
            destination = transcode.to_flac(destination)
        except (transcode.TranscodeError, subprocess.TimeoutExpired) as error:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=415, detail=str(error)) from error

    song = storage.create_song(
        song_id=song_id,
        title=payload.title.strip() or track.title,
        artist=payload.artist.strip() or track.artist,
        filename=destination.name,
        original_name=source.name,
        content_type="audio/mpeg",
        size_bytes=destination.stat().st_size,
        owner_id=auth.current_user_id(request),
    )
    # The analysis auto-continues to lyrics and stem separation, so a
    # downloaded track ends up fully prepared without another click.
    jobs.enqueue(song_id, destination.name)
    return song
