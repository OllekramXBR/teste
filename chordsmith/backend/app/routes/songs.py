"""Song library endpoints: upload, listing, playback, export."""

from __future__ import annotations

import json
import mimetypes
import re
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import jobs, library, storage, transcode
# `cifra` only pulls in the theory primitives, not librosa, so importing it at
# module level does not put the numba import back on the API's startup path.
from ..analysis import cifra, stems
from ..analysis import lyrics as lyrics_module
from ..config import (
    ALLOWED_EXTENSIONS,
    AUDIO_DIR,
    MAX_UPLOAD_BYTES,
    NATIVE_EXTENSIONS,
    STEM_FORMAT,
)
from ..midi import build_midi, build_multitrack

router = APIRouter(prefix="/api/songs", tags=["songs"])

CHUNK_SIZE = 256 * 1024
RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)")


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ")
    return " ".join(part for part in stem.split() if part).strip() or "Untitled"


@router.get("")
def list_songs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: str = Query("", max_length=120),
) -> dict:
    return {"songs": storage.list_songs(limit=limit, offset=offset, search=search)}


@router.post("", status_code=201)
async def upload_song(
    file: UploadFile = File(...),
    title: str = Form(""),
    artist: str = Form(""),
) -> dict:
    original_name = file.filename or "upload"
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported file type '{extension or 'unknown'}'. "
                f"Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )
    song_id = storage.new_id()
    stored_name = f"{song_id}{extension}"
    destination = AUDIO_DIR / stored_name
    destination.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                    )
                handle.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not store the upload: {exc}") from exc

    if size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The uploaded file is empty")

    if extension not in NATIVE_EXTENSIONS:
        # Converted once, here, so that every stage downstream sees a file
        # libsndfile can open and the pipeline never needs a second decoder.
        try:
            destination = transcode.to_flac(destination)
        except (transcode.TranscodeError, subprocess.TimeoutExpired) as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        stored_name = destination.name
        size = destination.stat().st_size

    song = storage.create_song(
        song_id=song_id,
        title=title.strip() or _title_from_filename(original_name),
        artist=artist.strip(),
        filename=stored_name,
        original_name=original_name,
        content_type=file.content_type or mimetypes.guess_type(original_name)[0] or "audio/mpeg",
        size_bytes=size,
    )
    jobs.enqueue(song_id, stored_name)
    return song


class ImportRequest(BaseModel):
    path: str = Field(max_length=1024)
    title: str = Field("", max_length=200)
    artist: str = Field("", max_length=200)


@router.post("/import", status_code=201)
def import_from_library(request: ImportRequest) -> dict:
    """Import a file that is already on the server.

    Copied rather than referenced. A song whose audio can disappear because
    somebody tidied a share is worse than a duplicated file: the analysis, the
    lyric and the stems would all outlive the thing they describe.
    """
    try:
        source = library.audio_file(request.path)
    except library.LibraryError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    song_id = storage.new_id()
    extension = source.suffix.lower()
    destination = AUDIO_DIR / f"{song_id}{extension}"
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.copy2(source, destination)
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not copy the file: {exc}") from exc

    if extension not in NATIVE_EXTENSIONS:
        try:
            destination = transcode.to_flac(destination)
        except (transcode.TranscodeError, subprocess.TimeoutExpired) as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=415, detail=str(exc)) from exc

    song = storage.create_song(
        song_id=song_id,
        title=request.title.strip() or _title_from_filename(source.name),
        artist=request.artist.strip(),
        filename=destination.name,
        original_name=source.name,
        content_type=mimetypes.guess_type(source.name)[0] or "audio/mpeg",
        size_bytes=destination.stat().st_size,
    )
    jobs.enqueue(song_id, destination.name)
    return song


@router.get("/{song_id}")
def get_song(song_id: str) -> dict:
    song = storage.get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


@router.delete("/{song_id}", status_code=204)
def delete_song(song_id: str) -> Response:
    filename = storage.delete_song(song_id)
    if filename is None:
        raise HTTPException(status_code=404, detail="Song not found")
    (AUDIO_DIR / filename).unlink(missing_ok=True)
    stems.delete_stems(song_id)
    return Response(status_code=204)


@router.post("/{song_id}/reanalyze")
def reanalyze(song_id: str) -> dict:
    stored = storage.get_song_file(song_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Song not found")
    if not (AUDIO_DIR / stored[0]).exists():
        raise HTTPException(status_code=410, detail="The audio file is no longer available")
    storage.set_status(song_id, "pending")
    jobs.enqueue(song_id, stored[0])
    return storage.get_song(song_id, include_analysis=False)  # type: ignore[return-value]


@router.post("/{song_id}/lyrics", status_code=202)
def transcribe_lyrics(
    song_id: str,
    model: str = Query("", max_length=40, description="Whisper size; empty uses the default"),
    force: bool = Query(False, description="Discard corrections made by hand"),
) -> dict:
    """Queue a lyric transcription for this song."""
    stored = storage.get_song_file(song_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Song not found")

    # Hand corrections outrank the model. Losing an evening's worth of them to a
    # stray click on "transcribe again" is the kind of thing that stops someone
    # trusting the tool with a set list.
    existing = storage.get_lyrics(song_id)
    if existing and existing.get("edited") and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                "This lyric was corrected by hand. Transcribing again would discard those "
                "corrections; repeat with force=true to do it anyway."
            ),
        )
    if not (AUDIO_DIR / stored[0]).exists():
        raise HTTPException(status_code=410, detail="The audio file is no longer available")
    jobs.enqueue_lyrics(song_id, stored[0], model.strip() or None)
    return storage.get_song(song_id, include_analysis=False)  # type: ignore[return-value]


@router.get("/{song_id}/lyrics")
def get_lyrics(song_id: str) -> dict:
    song = storage.get_song(song_id, include_analysis=False)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return {
        "status": song["lyricsStatus"],
        "error": song["lyricsError"],
        "lyrics": storage.get_lyrics(song_id),
    }


class LyricLine(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=2000)


class LyricEdit(BaseModel):
    segments: list[LyricLine] = Field(max_length=2000)


@router.put("/{song_id}/lyrics")
def edit_lyrics(song_id: str, edit: LyricEdit) -> dict:
    """Replace the transcribed lines with corrected ones.

    The recogniser will always get some words wrong, and a wrong word on a
    screen someone is singing from is not a cosmetic problem. Corrections are
    marked as such, and a later transcription refuses to overwrite them unless
    it is asked to.
    """
    song = storage.get_song(song_id, include_analysis=False)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")

    rebuilt = lyrics_module.rebuild_from_segments(
        [line.model_dump() for line in edit.segments], storage.get_lyrics(song_id)
    )
    storage.save_lyrics(song_id, rebuilt)
    return {"status": "ready", "lyrics": rebuilt}


@router.delete("/{song_id}/lyrics", status_code=204)
def delete_lyrics(song_id: str) -> Response:
    if not storage.get_song(song_id, include_analysis=False):
        raise HTTPException(status_code=404, detail="Song not found")
    storage.set_lyrics_status(song_id, "none")
    storage.clear_lyrics(song_id)
    return Response(status_code=204)


@router.post("/stems/all", status_code=202)
def separate_everything() -> dict:
    """Queue separation for the whole library, one song at a time."""
    queued = jobs.enqueue_all_stems()
    return {"queued": len(queued), "songs": queued}


@router.post("/{song_id}/stems", status_code=202)
def separate_stems(
    song_id: str,
    quality: str = Query("", description="'fast' or 'best'; empty uses the configured default"),
) -> dict:
    """Queue the two-pass separation for this song."""
    stored = storage.get_song_file(song_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Song not found")
    if not (AUDIO_DIR / stored[0]).exists():
        raise HTTPException(status_code=410, detail="The audio file is no longer available")
    jobs.enqueue_stems(song_id, stored[0], quality.strip() or None)
    return storage.get_song(song_id, include_analysis=False)  # type: ignore[return-value]


@router.get("/{song_id}/stems")
def list_stems(song_id: str) -> dict:
    song = storage.get_song(song_id, include_analysis=False)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    return {
        "status": song["stemsStatus"],
        "error": song["stemsError"],
        "stems": [
            {**stem.to_dict(), "url": f"/api/songs/{song_id}/stems/{stem.name}"}
            for stem in stems.available_stems(song_id)
        ],
    }


@router.delete("/{song_id}/stems", status_code=204)
def remove_stems(song_id: str) -> Response:
    if not storage.get_song(song_id, include_analysis=False):
        raise HTTPException(status_code=404, detail="Song not found")
    stems.delete_stems(song_id)
    storage.set_stems_status(song_id, "none")
    return Response(status_code=204)


@router.get("/{song_id}/stems/{name}")
def stream_stem(song_id: str, name: str) -> FileResponse:
    """Serve one stem.

    Plain FileResponse rather than the ranged reader used for the original
    audio: the stage view fetches each stem whole and decodes it into memory
    before playback, so there is nothing to seek within.
    """
    path = stems.stem_path(song_id, name)
    if path is None:
        raise HTTPException(status_code=404, detail="That stem has not been produced")
    return FileResponse(
        path,
        media_type=f"audio/{STEM_FORMAT}",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/{song_id}/cifra")
def download_cifra(
    song_id: str,
    transpose: int = Query(0, ge=-11, le=11),
    capo: int = Query(0, ge=0, le=11),
    simplify: bool = Query(True, description="Collapse decoder extensions to playable triads"),
    format: str = Query("columns", pattern="^(columns|chordpro)$"),
    download: bool = Query(False),
) -> Response:
    """The chart in Brazilian cifra format: chords above the words, plain text."""
    song = storage.get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    analysis = song.get("analysis")
    if not analysis:
        raise HTTPException(status_code=409, detail="This song has not been analysed yet")

    build = cifra.render_chordpro if format == "chordpro" else cifra.render
    text = build(
        analysis,
        song.get("lyrics"),
        title=song["title"],
        artist=song["artist"],
        transpose=transpose,
        capo=capo,
        simplify=simplify,
    )
    headers = {}
    if download:
        safe_title = re.sub(r"[^\w\- ]+", "", song["title"]).strip() or "cifra"
        suffix = "cho" if format == "chordpro" else "txt"
        headers["Content-Disposition"] = f'attachment; filename="{safe_title}.{suffix}"'
    return Response(content=text, media_type="text/plain; charset=utf-8", headers=headers)


@router.get("/{song_id}/audio")
def stream_audio(song_id: str, request: Request):
    """Serve the audio with HTTP range support so the player can seek."""
    stored = storage.get_song_file(song_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Song not found")

    filename, original_name, content_type = stored
    path = AUDIO_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=410, detail="The audio file is no longer available")

    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(
            path,
            media_type=content_type or "application/octet-stream",
            filename=original_name,
            headers={"Accept-Ranges": "bytes"},
        )

    match = RANGE_PATTERN.fullmatch(range_header.strip())
    if not match:
        raise HTTPException(status_code=400, detail="Malformed Range header")

    raw_start, raw_end = match.groups()
    if raw_start:
        start = int(raw_start)
        end = int(raw_end) if raw_end else file_size - 1
    else:
        # Suffix form: "bytes=-500" means the final 500 bytes.
        if not raw_end:
            raise HTTPException(status_code=400, detail="Malformed Range header")
        start = max(file_size - int(raw_end), 0)
        end = file_size - 1

    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        return Response(
            status_code=416, headers={"Content-Range": f"bytes */{file_size}"}
        )

    length = end - start + 1

    def iter_range():
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_range(),
        status_code=206,
        media_type=content_type or "application/octet-stream",
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/{song_id}/midi")
def download_midi(
    song_id: str,
    transpose: int = Query(0, ge=-11, le=11),
    tracks: str = Query("chords", pattern="^(chords|multi)$"),
) -> Response:
    song = storage.get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    analysis = song.get("analysis")
    if not analysis:
        raise HTTPException(status_code=409, detail="This song has not been analysed yet")

    if tracks == "multi":
        if not stems.available_stems(song_id):
            raise HTTPException(
                status_code=409,
                detail="Separate this song into stems first — a multitrack export needs them.",
            )
        cached = stems.STEMS_DIR / song_id / "tracks.json"
        if not cached.exists():
            # Transcribing three stems is minutes of work, so it is queued and
            # the caller comes back rather than holding a request open.
            jobs.enqueue_multitrack(song_id)
            raise HTTPException(
                status_code=202,
                detail="Transcribing each stem. Try again in a few minutes.",
            )
        data = build_multitrack(
            chords=analysis.get("chords", []),
            tracks=json.loads(cached.read_text(encoding="utf-8")),
            bpm=analysis.get("bpm") or 120,
            beats_per_bar=analysis.get("beatsPerBar", 4),
            transpose=transpose,
            title=song["title"],
        )
        safe = re.sub(r"[^\w\- ]+", "", song["title"]).strip() or "chart"
        return Response(
            content=data,
            media_type="audio/midi",
            headers={"Content-Disposition": f'attachment; filename="{safe} (multipista).mid"'},
        )

    data = build_midi(
        chords=analysis.get("chords", []),
        bpm=analysis.get("bpm") or 120,
        beats_per_bar=analysis.get("beatsPerBar", 4),
        transpose=transpose,
        title=song["title"],
    )
    safe_title = re.sub(r"[^\w\- ]+", "", song["title"]).strip() or "chords"
    return Response(
        content=data,
        media_type="audio/midi",
        headers={"Content-Disposition": f'attachment; filename="{safe_title}.mid"'},
    )


def audio_dir_size() -> int:
    """Total bytes stored on disk, used by the health endpoint."""
    if not AUDIO_DIR.exists():
        return 0
    return sum(entry.stat().st_size for entry in AUDIO_DIR.iterdir() if entry.is_file())
