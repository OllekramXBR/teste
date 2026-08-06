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

CREATE TABLE IF NOT EXISTS setlists (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    notes      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- The order of a set is the whole point of a set, so position is stored
-- explicitly rather than inferred from insertion. ON DELETE CASCADE means
-- deleting a song cannot leave a set pointing at a hole.
CREATE TABLE IF NOT EXISTS setlist_songs (
    setlist_id TEXT NOT NULL REFERENCES setlists (id) ON DELETE CASCADE,
    song_id    TEXT NOT NULL REFERENCES songs (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL,
    PRIMARY KEY (setlist_id, song_id)
);
CREATE INDEX IF NOT EXISTS setlist_order ON setlist_songs (setlist_id, position);
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
    # NULL owner means "from before there were accounts", and those stay visible
    # to everyone: a library that silently disappears the day a login is turned
    # on is not a migration, it is a data loss report.
    "owner_id": "ALTER TABLE songs ADD COLUMN owner_id TEXT",
    "shared": "ALTER TABLE songs ADD COLUMN shared INTEGER NOT NULL DEFAULT 1",
}

SETLIST_MIGRATIONS: dict[str, str] = {
    "owner_id": "ALTER TABLE setlists ADD COLUMN owner_id TEXT",
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

        on_setlists = {row["name"] for row in connection.execute("PRAGMA table_info(setlists)")}
        for column, statement in SETLIST_MIGRATIONS.items():
            if column not in on_setlists:
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
    owner_id: str | None = None,
    shared: bool = True,
) -> dict[str, Any]:
    timestamp = _now()
    with _write_lock, connect() as connection:
        connection.execute(
            """
            INSERT INTO songs (id, title, artist, filename, original_name, content_type,
                               size_bytes, status, created_at, updated_at, owner_id, shared)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
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
                owner_id,
                1 if shared else 0,
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
        "ownerId": row["owner_id"],
        "shared": bool(row["shared"]),
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


def list_songs(
    limit: int = 100,
    offset: int = 0,
    search: str = "",
    viewer_id: str | None = None,
) -> list[dict[str, Any]]:
    """Songs this viewer may see.

    ``viewer_id`` of ``None`` means accounts are not being enforced, and
    everything is listed — which is how this app has always behaved. With a
    viewer, the library is their own songs plus anything marked shared plus
    anything that predates accounts, because a song nobody owns belongs to the
    house.
    """
    query = "SELECT * FROM songs"
    where: list[str] = []
    params: list[Any] = []

    if search:
        where.append("(title LIKE ? OR artist LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if viewer_id is not None:
        where.append("(owner_id = ? OR owner_id IS NULL OR shared = 1)")
        params.append(viewer_id)
    if where:
        query += " WHERE " + " AND ".join(where)

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


def set_song_sharing(song_id: str, shared: bool) -> bool:
    """Whether other people on this server can see the song."""
    with _write_lock, connect() as connection:
        cursor = connection.execute(
            "UPDATE songs SET shared = ?, updated_at = ? WHERE id = ?",
            (1 if shared else 0, _now(), song_id),
        )
    return cursor.rowcount > 0


def create_setlist(name: str, notes: str = "", owner_id: str | None = None) -> dict[str, Any]:
    setlist_id = new_id()
    timestamp = _now()
    with _write_lock, connect() as connection:
        connection.execute(
            """
            INSERT INTO setlists (id, name, notes, created_at, updated_at, owner_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (setlist_id, name, notes, timestamp, timestamp, owner_id),
        )
    return get_setlist(setlist_id)  # type: ignore[return-value]


def get_setlist(setlist_id: str) -> dict[str, Any] | None:
    """A setlist with its songs, in playing order.

    The songs carry enough of themselves to draw a stage list — title, key,
    tempo, and whether the lyric and stems are ready — without a second request
    per song while someone is standing in front of an audience.
    """
    with connect() as connection:
        row = connection.execute("SELECT * FROM setlists WHERE id = ?", (setlist_id,)).fetchone()
        if not row:
            return None
        songs = connection.execute(
            """
            SELECT s.*, ls.position
              FROM setlist_songs ls
              JOIN songs s ON s.id = ls.song_id
             WHERE ls.setlist_id = ?
             ORDER BY ls.position
            """,
            (setlist_id,),
        ).fetchall()

    return {
        "id": row["id"],
        "name": row["name"],
        "notes": row["notes"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "songs": [_row_to_song(song, include_analysis=False) for song in songs],
    }


def list_setlists(viewer_id: str | None = None) -> list[dict[str, Any]]:
    """Setlists this viewer may see.

    Unlike songs, a set is not shared by default. A running order is a personal
    thing — two people playing the same songs on different nights want their own
    — so with accounts enforced you see your own and the ones that predate
    accounts, and nobody else's.
    """
    where = "" if viewer_id is None else " WHERE l.owner_id = ? OR l.owner_id IS NULL"
    params = [] if viewer_id is None else [viewer_id]
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT l.*, COUNT(ls.song_id) AS songs
              FROM setlists l
              LEFT JOIN setlist_songs ls ON ls.setlist_id = l.id
              {where}
             GROUP BY l.id
             ORDER BY l.updated_at DESC
            """,
            params,
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "notes": row["notes"],
            "songCount": row["songs"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]


def update_setlist(setlist_id: str, name: str | None, notes: str | None) -> bool:
    with _write_lock, connect() as connection:
        cursor = connection.execute(
            """
            UPDATE setlists
               SET name = COALESCE(?, name), notes = COALESCE(?, notes), updated_at = ?
             WHERE id = ?
            """,
            (name, notes, _now(), setlist_id),
        )
    return cursor.rowcount > 0


def delete_setlist(setlist_id: str) -> bool:
    with _write_lock, connect() as connection:
        cursor = connection.execute("DELETE FROM setlists WHERE id = ?", (setlist_id,))
    return cursor.rowcount > 0


def set_setlist_songs(setlist_id: str, song_ids: list[str]) -> bool:
    """Replace the whole running order in one transaction.

    Replacing rather than patching: reordering, adding and removing are the same
    operation from the client's point of view, and a set that is briefly missing
    a song because two requests interleaved is not a state worth being able to
    reach.
    """
    with _write_lock, connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM setlists WHERE id = ?", (setlist_id,)
        ).fetchone()
        if not exists:
            return False
        connection.execute("DELETE FROM setlist_songs WHERE setlist_id = ?", (setlist_id,))
        connection.executemany(
            "INSERT INTO setlist_songs (setlist_id, song_id, position) VALUES (?, ?, ?)",
            [(setlist_id, song_id, index) for index, song_id in enumerate(song_ids)],
        )
        connection.execute(
            "UPDATE setlists SET updated_at = ? WHERE id = ?", (_now(), setlist_id)
        )
    return True


def stale_processing_ids() -> Iterable[str]:
    """Songs left mid-analysis by a process that died; they need requeueing."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT id FROM songs WHERE status IN ('pending', 'analyzing')"
        ).fetchall()
    return [row["id"] for row in rows]
