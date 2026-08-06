"""Tests for deciding whether two files are the same recording.

By content, not by name — the case that started this was one recording filed
under two names in two folders, which a name check would have missed twice.
"""

from __future__ import annotations

import pytest

from app import storage
from app.fingerprint import of_file


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATABASE_PATH", tmp_path / "test.db")
    storage.init_db()
    return tmp_path


def write(path, data: bytes):
    path.write_bytes(data)
    return path


class TestHashing:
    def test_the_same_bytes_hash_the_same_under_different_names(self, tmp_path):
        one = write(tmp_path / "musica.mp3", b"identical" * 5000)
        two = write(tmp_path / "00 4 3 outra copia.mp3", b"identical" * 5000)
        assert of_file(one) == of_file(two)

    def test_different_bytes_hash_differently(self, tmp_path):
        one = write(tmp_path / "a.mp3", b"aaaa" * 5000)
        two = write(tmp_path / "b.mp3", b"bbbb" * 5000)
        assert of_file(one) != of_file(two)

    def test_a_file_larger_than_one_chunk_is_read_whole(self, tmp_path):
        # A hash that stopped at the first megabyte would call two albums equal
        # whenever their first megabyte matched.
        from app.fingerprint import CHUNK

        one = write(tmp_path / "a.mp3", b"x" * (CHUNK + 10) + b"final-a")
        two = write(tmp_path / "b.mp3", b"x" * (CHUNK + 10) + b"final-b")
        assert of_file(one) != of_file(two)

    def test_an_empty_file_still_hashes(self, tmp_path):
        assert of_file(write(tmp_path / "vazio.mp3", b""))


class TestLookup:
    def add(self, digest: str, title: str) -> str:
        song_id = storage.new_id()
        storage.create_song(
            song_id=song_id,
            title=title,
            artist="",
            filename=f"{song_id}.mp3",
            original_name=f"{title}.mp3",
            content_type="audio/mpeg",
            size_bytes=1,
            audio_sha256=digest,
        )
        return song_id

    def test_a_stored_hash_is_found_again(self, db):
        self.add("abc123", "Conversa Fiada")
        assert storage.find_by_hash("abc123")["title"] == "Conversa Fiada"

    def test_an_unknown_hash_finds_nothing(self, db):
        assert storage.find_by_hash("nunca-visto") is None

    def test_songs_from_before_hashing_do_not_collide_with_each_other(self, db):
        # Their hash is NULL, and NULL must not match NULL — otherwise the first
        # import after this change would be refused as a duplicate of an old
        # song it has nothing to do with.
        self.add(None, "antiga um")
        self.add(None, "antiga dois")
        assert storage.find_by_hash(None) is None

    def test_the_duplicate_is_reported_by_name_so_the_message_can_say_which(self, db):
        self.add("abc123", "Conversa Fiada")
        found = storage.find_by_hash("abc123")
        assert found is not None and found["title"]
