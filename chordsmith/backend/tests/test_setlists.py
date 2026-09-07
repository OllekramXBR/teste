"""Tests for setlists.

The running order is the point, so most of these are about order surviving the
things that happen to it: reordering, removing a song from the library, adding
the same song twice by accident.
"""

from __future__ import annotations

import pytest

from app import storage


@pytest.fixture
def db(tmp_path, monkeypatch):
    # `connect()` reads the module-level name, so pointing that at a temporary
    # file is enough to keep these tests off the real library.
    monkeypatch.setattr(storage, "DATABASE_PATH", tmp_path / "test.db")
    storage.init_db()
    return tmp_path


def make_song(title: str) -> str:
    song_id = storage.new_id()
    storage.create_song(
        song_id=song_id,
        title=title,
        artist="",
        filename=f"{song_id}.mp3",
        original_name=f"{title}.mp3",
        content_type="audio/mpeg",
        size_bytes=1,
    )
    return song_id


class TestOrder:
    def test_songs_come_back_in_the_order_they_were_set(self, db):
        setlist = storage.create_setlist("Show de sexta")
        first, second, third = make_song("A"), make_song("B"), make_song("C")
        storage.set_setlist_songs(setlist["id"], [third, first, second])

        titles = [song["title"] for song in storage.get_setlist(setlist["id"])["songs"]]
        assert titles == ["C", "A", "B"]

    def test_reordering_replaces_the_whole_order(self, db):
        setlist = storage.create_setlist("Show")
        a, b = make_song("A"), make_song("B")
        storage.set_setlist_songs(setlist["id"], [a, b])
        storage.set_setlist_songs(setlist["id"], [b, a])

        titles = [song["title"] for song in storage.get_setlist(setlist["id"])["songs"]]
        assert titles == ["B", "A"]

    def test_removing_a_song_from_the_set_leaves_the_rest_in_order(self, db):
        setlist = storage.create_setlist("Show")
        a, b, c = make_song("A"), make_song("B"), make_song("C")
        storage.set_setlist_songs(setlist["id"], [a, b, c])
        storage.set_setlist_songs(setlist["id"], [a, c])

        titles = [song["title"] for song in storage.get_setlist(setlist["id"])["songs"]]
        assert titles == ["A", "C"]

    def test_an_empty_set_is_allowed(self, db):
        setlist = storage.create_setlist("Vazio")
        storage.set_setlist_songs(setlist["id"], [make_song("A")])
        storage.set_setlist_songs(setlist["id"], [])
        assert storage.get_setlist(setlist["id"])["songs"] == []


class TestIntegrity:
    def test_deleting_a_song_removes_it_from_every_set(self, db):
        # Otherwise a set would point at a hole, and it would point at it on
        # stage, which is the worst possible moment to find out.
        setlist = storage.create_setlist("Show")
        a, b = make_song("A"), make_song("B")
        storage.set_setlist_songs(setlist["id"], [a, b])
        storage.delete_song(a)

        titles = [song["title"] for song in storage.get_setlist(setlist["id"])["songs"]]
        assert titles == ["B"]

    def test_deleting_a_set_does_not_delete_its_songs(self, db):
        setlist = storage.create_setlist("Show")
        song = make_song("A")
        storage.set_setlist_songs(setlist["id"], [song])
        storage.delete_setlist(setlist["id"])
        assert storage.get_song(song) is not None

    def test_setting_songs_on_a_set_that_does_not_exist_fails(self, db):
        assert storage.set_setlist_songs("nope", [make_song("A")]) is False


class TestListing:
    def test_sets_report_how_many_songs_they_hold(self, db):
        setlist = storage.create_setlist("Show")
        storage.set_setlist_songs(setlist["id"], [make_song("A"), make_song("B")])
        listed = next(item for item in storage.list_setlists() if item["id"] == setlist["id"])
        assert listed["songCount"] == 2

    def test_an_empty_set_reports_zero_rather_than_disappearing(self, db):
        setlist = storage.create_setlist("Novo")
        listed = next(item for item in storage.list_setlists() if item["id"] == setlist["id"])
        assert listed["songCount"] == 0

    def test_renaming_keeps_the_songs(self, db):
        setlist = storage.create_setlist("Antigo")
        storage.set_setlist_songs(setlist["id"], [make_song("A")])
        storage.update_setlist(setlist["id"], "Novo nome", None)

        updated = storage.get_setlist(setlist["id"])
        assert updated["name"] == "Novo nome"
        assert len(updated["songs"]) == 1

    def test_a_missing_set_reads_as_missing(self, db):
        assert storage.get_setlist("nope") is None
