"""Web chart search, import and comparison against the detected analysis.

The library owns the *heard* harmony of a song; Cifra Club owns the *written*
one. These endpoints bridge the two: search the site, fetch and store a chart,
then ask how often the chart and the analysis agree — the verdicts a renderer
paints over the chord cells.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .. import cifraclub, storage

router = APIRouter(prefix="/api/cifraclub", tags=["cifraclub"])
song_router = APIRouter(prefix="/api/songs", tags=["cifraclub"])

# Cifra Club slugs are lower-case letters, digits and hyphens. Keeping the
# import URL to that shape is what stops a dns/url pair from being a way to ask
# the server to fetch an arbitrary page.
_SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")


@router.get("/search")
def search(
    q: str = Query("", max_length=200),
    limit: int = Query(12, ge=1, le=25),
) -> dict:
    """Songs on Cifra Club that match the query."""
    query = q.strip()
    if not query:
        return {"results": []}
    try:
        results = cifraclub.search(query, limit)
    except cifraclub.CifraclubError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"results": [result.to_dict() for result in results]}


class ImportRequest(BaseModel):
    dns: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=200)
    source_id: int = Field(ge=0)
    title: str = Field("", max_length=200)
    artist: str = Field("", max_length=200)
    album: str = Field("", max_length=200)
    image: str = Field("", max_length=500)


@song_router.post("/{song_id}/cifraclub/import", status_code=201)
def import_chart(song_id: str, payload: ImportRequest) -> dict:
    """Fetch the chart at ``/dns/url/`` and keep it as the song's web chart.

    The page is fetched by the server from the slugs the client saw in its own
    search results, so a client can ask for a chart it was shown and nothing
    else. The fetched metadata wins over what the client sent; the client's
    title and artist only fill a gap the page itself leaves open.
    """
    if not _SLUG_PATTERN.fullmatch(payload.dns) or not _SLUG_PATTERN.fullmatch(payload.url):
        raise HTTPException(status_code=422, detail="Invalid chart address")
    song = storage.get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    try:
        chart = cifraclub.fetch_chart(payload.dns, payload.url)
    except cifraclub.CifraclubError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    source = chart["source"]
    return storage.save_cifra(
        song_id=song_id,
        source_id=source["id"] or payload.source_id,
        title=source["title"] or payload.title or song["title"],
        artist=source["artist"] or payload.artist or song["artist"],
        album=source["album"] or payload.album,
        image=source["image"] or payload.image,
        page_url=f"/{payload.dns}/{payload.url}/",
        key=source["key"],
        composers=source["composers"],
        chords=chart["chords"],
        lines=chart["lines"],
    )


@song_router.get("/{song_id}/cifraclub")
def get_chart(song_id: str) -> dict:
    """The web chart stored for this song, so the view never refetches it."""
    song = storage.get_song(song_id, include_analysis=False)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    chart = storage.get_cifra(song_id)
    if not chart:
        raise HTTPException(status_code=404, detail="No web chart imported for this song")
    return chart


@song_router.delete("/{song_id}/cifraclub")
def remove_chart(song_id: str) -> dict:
    """Drop the imported web chart and with it the comparison marks."""
    song = storage.get_song(song_id, include_analysis=False)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    if not storage.delete_cifra(song_id):
        raise HTTPException(status_code=404, detail="No web chart imported for this song")
    return {"ok": True}


@song_router.get("/{song_id}/cifraclub/compare")
def compare_chart(song_id: str) -> dict:
    """How the imported web chart and the detected analysis agree."""
    song = storage.get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    analysis = song.get("analysis")
    if not analysis:
        raise HTTPException(status_code=409, detail="This song has not been analysed yet")
    chart = storage.get_cifra(song_id)
    if not chart:
        raise HTTPException(status_code=404, detail="No web chart imported for this song")

    result = cifraclub.compare(analysis, chart["chords"])
    result["web"] = {
        "title": chart["title"],
        "artist": chart["artist"],
        "album": chart["album"],
        "image": chart["image"],
        "key": chart["key"],
        "composers": chart["composers"],
        "chordCount": len(chart["chords"]),
    }
    detected_key = (analysis.get("key") or {}).get("name") or ""
    result["detectedKey"] = detected_key
    result["webKey"] = chart["key"]
    return result


@song_router.post("/{song_id}/cifraclub/correct")
def correct_chart(song_id: str) -> dict:
    """Rewrite the detected analysis with the imported chart as the authority.

    The chart's tom and chord letters replace the detected ones, and its lyric
    lines replace the transcribed words. Everything that describes *when* —
    beats, bars, timing and confidence, and the segments' starts and ends when
    the transcription line count matches the chart's — stays from the audio.
    The reader asks for this once the comparison shows the chart is the
    version they want to play. The updated song is returned so the page can
    redraw itself against it.
    """
    song = storage.get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    analysis = song.get("analysis")
    if not analysis:
        raise HTTPException(status_code=409, detail="This song has not been analysed yet")
    chart = storage.get_cifra(song_id)
    if not chart:
        raise HTTPException(status_code=404, detail="No web chart imported for this song")

    corrected = cifraclub.correct(analysis, chart["chords"], chart["key"])
    storage.save_analysis(song_id, corrected)

    corrected_lyrics = cifraclub.correct_lyrics(chart, storage.get_lyrics(song_id))
    if corrected_lyrics is not None:
        storage.save_lyrics(song_id, corrected_lyrics)
    return storage.get_song(song_id)  # type: ignore[return-value]
