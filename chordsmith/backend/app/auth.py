"""Accounts, sessions and ownership.

**Off by default, and that is deliberate.** This app has run without any
authentication, behind a Tailscale network, and turning a login on by surprise
would lock its owner out of their own library at the worst possible moment.
``CHORDSMITH_AUTH`` has to be set to ``required`` before anything here refuses a
request; until then accounts can be created and used, and everything keeps
working exactly as it did for anyone who has not signed in.

Passwords are hashed with PBKDF2-HMAC-SHA256 and a per-user salt, from the
standard library — no new dependency, and a work factor that can be raised
without invalidating existing hashes because it is stored alongside them.

Sessions are opaque random tokens kept server-side rather than signed claims in
a cookie. It costs one query per request and buys the ability to actually revoke
a session, which a self-contained token cannot offer.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import AUTH_MODE, SESSION_DAYS
from .storage import _now, _write_lock, connect, new_id

# Raising this only affects passwords set from then on: the cost used is stored
# with each hash, so old ones keep verifying at the cost they were made with.
ITERATIONS = 210_000
SESSION_COOKIE = "metatron_session"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions (user_id);
"""


class AuthError(Exception):
    """A credential that does not check out, or a name already taken."""


def init() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)


def enabled() -> bool:
    """Whether a request without a session should be refused."""
    return AUTH_MODE == "required"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt, expected = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), int(rounds)
    )
    # Constant-time: a comparison that returns early leaks how much of the hash
    # matched, one byte at a time.
    return hmac.compare_digest(digest.hex(), expected)


def create_user(username: str, password: str, display_name: str = "") -> dict[str, Any]:
    username = username.strip()
    if len(username) < 3:
        raise AuthError("O nome de usuário precisa de ao menos 3 caracteres")
    if len(password) < 8:
        raise AuthError("A senha precisa de ao menos 8 caracteres")

    user_id = new_id()
    try:
        with _write_lock, connect() as connection:
            connection.execute(
                """
                INSERT INTO users (id, username, display_name, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, username, display_name.strip(), hash_password(password), _now()),
            )
    except sqlite3.IntegrityError as error:
        raise AuthError("Esse nome de usuário já existe") from error
    return {"id": user_id, "username": username, "displayName": display_name.strip()}


def authenticate(username: str, password: str) -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()

    # The same message and the same work either way: answering faster for an
    # unknown user than for a wrong password tells an attacker which names exist.
    stored = row["password_hash"] if row else hash_password(secrets.token_hex(8))
    if not verify_password(password, stored) or row is None:
        raise AuthError("Usuário ou senha incorretos")

    return {"id": row["id"], "username": row["username"], "displayName": row["display_name"]}


def start_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with _write_lock, connect() as connection:
        connection.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, _now(), expires.isoformat(timespec="seconds")),
        )
    return token


def user_for_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with connect() as connection:
        row = connection.execute(
            """
            SELECT u.id, u.username, u.display_name, s.expires_at
              FROM sessions s JOIN users u ON u.id = s.user_id
             WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
    if not row:
        return None
    if row["expires_at"] < _now():
        end_session(token)
        return None
    return {"id": row["id"], "username": row["username"], "displayName": row["display_name"]}


def end_session(token: str | None) -> None:
    if not token:
        return
    with _write_lock, connect() as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))


def current_user_id(request) -> str | None:
    """Who is signed in, whether or not accounts are being enforced.

    Used when something is created, so that a song uploaded by a signed-in user
    is theirs even while the server is still letting everyone in.
    """
    user = user_for_token(request.cookies.get(SESSION_COOKIE))
    return user["id"] if user else None


def viewer_id(request) -> str | None:
    """Whose library to show, or ``None`` to show everything.

    ``None`` when accounts are not enforced, which keeps the app behaving
    exactly as it did before they existed.
    """
    return current_user_id(request) if enabled() else None


def count_users() -> int:
    with connect() as connection:
        return int(connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])
