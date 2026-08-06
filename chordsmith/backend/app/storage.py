"""SQLite persistence for songs and their analysis results.

Deliberately dependency-free: one small table, JSON blobs for the analysis, and
a connection per call. At the scale this app runs at, an ORM would be more
machinery than the problem needs.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import DATABASE_PATH, ensure_directories

_write_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS songs (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    artist        TEXT NOT NULL DEFAULT '',
    filename      TEXT NOT NULL,
    original_name TEXT NOT NULL,
    content_type  TEXT NOT NULL DEFAULT '',
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'pending',
    error         TEXT,
    duration      REAL,
    bpm           REAL,
    key_name      TEXT,
    analysis      TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS songs_created_at ON songs (created_at DESC);
"""

# Columns added after the first release. SQLite has no "ADD COLUMN IF NOT
# EXISTS", so they are applied by comparing against the live table — a library
# recorded before lyrics existed keeps its rows and simply gains empty ones.
MIGRATIONS: dict[str, str] = {
    "lyrics": "ALTER TABLE songs ADD COLUMN lyrics TEXT",
    "lyrics_status": "ALTER TABLE songs ADD COLUMN lyrics_status TEXT NOT NULL DEFAULT 'none'",
    "lyrics_error": "ALTER TABLE songs ADD COLUMN lyrics_error TEXT",
    "stems_status": "ALTER TABLE songs ADD COLUMN stems_status TEXT NOT NULL DEFAULT 'none'",
    "stems_error": "ALTER TABLE songs ADD COLUMN stems_error TEXT",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    ensure_directories()
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)
        existing = {row["name"] for row in connection.execute("PRAGMA table_info(songs)")}
        for column, statement in MIGRATIONS.items():
            if column not in existing:
                connection.execute(statement)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def create_song(
    song_id: str,
    title: str,
    artist: str,
    filename: str,
    original_name: str,
    content_type: str,
    size_bytes: int,
) -> dict[str, Any]:
    timestamp = _now()
    with _write_lock, connect() as connection:
        connection.execute(
            """
            INSERT INTO songs (id, title, artist, filename, original_name, content_type,
                               size_bytes, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                song_id,
                title,
                artist,
                filename,
                original_name,
                content_type,
                size_bytes,
                timestamp,
                timestamp,
            ),
        )
    return get_song(song_id)  # type: ignore[return-value]


def set_status(song_id: str, status: str, error: str | None = None) -> None:
    with _write_lock, connect() as connection:
        connection.execute(
            "UPDATE songs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, error, _now(), song_id),
        )


def save_analysis(song_id: str, analysis: dict[str, Any]) -> None:
    with _write_lock, connect() as connection:
        connection.execute(
            """
            UPDATE songs
               SET status = 'ready', error = NULL, analysis = ?, duration = ?,
                   bpm = ?, key_name = ?, updated_at = ?
             WHERE id = ?
            """,
            (
                json.dumps(analysis, separators=(",", ":")),
                analysis.get("duration"),
                analysis.get("bpm"),
                (analysis.get("key") or {}).get("name"),
                _now(),
                song_id,
            ),
        )


def set_lyrics_status(song_id: str, status: str, error: str | None = None) -> None:
    with _write_lock, connect() as connection:
        connection.execute(
            "UPDATE songs SET lyrics_status = ?, lyrics_error = ?, updated_at = ? WHERE id = ?",
            (status, error, _now(), song_id),
        )


def save_lyrics(song_id: str, lyrics: dict[str, Any]) -> None:
    with _write_lock, connect() as connection:
        connection.execute(
            """
            UPDATE songs
               SET lyrics = ?, lyrics_status = 'ready', lyrics_error = NULL, updated_at = ?
             WHERE id = ?
            """,
            (json.dumps(lyrics, separators=(",", ":"), ensure_ascii=False), _now(), song_id),
        )


def clear_lyrics(song_id: str) -> None:
    with _write_lock, connect() as connection:
        connection.execute(
            "UPDATE songs SET lyrics = NULL, updated_at = ? WHERE id = ?", (_now(), song_id)
        )


def get_lyrics(song_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT lyrics FROM songs WHERE id = ?", (song_id,)).fetchone()
    if not row or not row["lyrics"]:
        return None
    return json.loads(row["lyrics"])


def stale_lyrics_ids() -> Iterable[str]:
    """Transcriptions left mid-flight by a process that died."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM songs WHERE lyrics_status IN ('pending', 'transcribing')"
        ).fetchall()
    return [row["id"] for row in rows]


def set_stems_status(song_id: str, status: str, error: str | None = None) -> None:
    with _write_lock, connect() as connection:
        connection.execute(
            "UPDATE songs SET stems_status = ?, stems_error = ?, updated_at = ? WHERE id = ?",
            (status, error, _now(), song_id),
        )


def stale_stems_ids() -> Iterable[str]:
    """Separations left mid-flight by a process that died."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM songs WHERE stems_status IN ('pending', 'separating')"
        ).fetchall()
    return [row["id"] for row in rows]


def _row_to_song(row: sqlite3.Row, include_analysis: bool) -> dict[str, Any]:
    song = {
        "id": row["id"],
        "title": row["title"],
        "artist": row["artist"],
        "originalName": row["original_name"],
        "contentType": row["content_type"],
        "sizeBytes": row["size_bytes"],
        "status": row["status"],
        "error": row["error"],
        "duration": row["duration"],
        "bpm": row["bpm"],
        "keyName": row["key_name"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "audioUrl": f"/api/songs/{row['id']}/audio",
        "lyricsStatus": row["lyrics_status"] or "none",
        "lyricsError": row["lyrics_error"],
        "stemsStatus": row["stems_status"] or "none",
        "stemsError": row["stems_error"],
    }
    if include_analysis:
        song["analysis"] = json.loads(row["analysis"]) if row["analysis"] else None
        song["lyrics"] = json.loads(row["lyrics"]) if row["lyrics"] else None
    return song


def get_song(song_id: str, include_analysis: bool = True) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
    return _row_to_song(row, include_analysis) if row else None


def get_song_file(song_id: str) -> tuple[str, str, str] | None:
    """Return ``(filename, original_name, content_type)`` for a stored song."""
    with connect() as connection:
        row = connection.execute(
            "SELECT filename, original_name, content_type FROM songs WHERE id = ?", (song_id,)
        ).fetchone()
    if not row:
        return None
    return row["filename"], row["original_name"], row["content_type"]


def list_songs(limit: int = 100, offset: int = 0, search: str = "") -> list[dict[str, Any]]:
    query = "SELECT * FROM songs"
    params: list[Any] = []
    if search:
        query += " WHERE title LIKE ? OR artist LIKE ?"
        params += [f"%{search}%", f"%{search}%"]
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    with connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return [_row_to_song(row, include_analysis=False) for row in rows]


def delete_song(song_id: str) -> str | None:
    """Delete a song row, returning the stored filename so the caller can unlink it."""
    with _write_lock, connect() as connection:
        row = connection.execute("SELECT filename FROM songs WHERE id = ?", (song_id,)).fetchone()
        if not row:
            return None
        connection.execute("DELETE FROM songs WHERE id = ?", (song_id,))
    return row["filename"]


def stale_processing_ids() -> Iterable[str]:
    """Songs left mid-analysis by a process that died; they need requeueing."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM songs WHERE status IN ('pending', 'analyzing')"
        ).fetchall()
    return [row["id"] for row in rows]
