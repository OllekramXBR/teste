"""Song library endpoints: upload, listing, playback, export."""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from .. import jobs, storage
from ..config import ALLOWED_EXTENSIONS, AUDIO_DIR, MAX_UPLOAD_BYTES, NATIVE_EXTENSIONS
from ..midi import build_midi

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
    if extension not in NATIVE_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"'{extension}' needs ffmpeg, which is not installed. "
                "Convert the file to MP3, WAV, FLAC or OGG first."
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
def download_midi(song_id: str, transpose: int = Query(0, ge=-11, le=11)) -> Response:
    song = storage.get_song(song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Song not found")
    analysis = song.get("analysis")
    if not analysis:
        raise HTTPException(status_code=409, detail="This song has not been analysed yet")

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
