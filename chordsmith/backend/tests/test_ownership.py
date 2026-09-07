"""Tests for who sees what once accounts exist.

The dangerous case is not a stranger seeing too much — this runs on a private
network — it is the owner seeing too little. A library that empties itself the
day a login is switched on is a data loss report wearing a migration's clothes,
so most of these check that nothing disappears.
"""

from __future__ import annotations

import pytest

from app import storage


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATABASE_PATH", tmp_path / "test.db")
    storage.init_db()
    return tmp_path


def add(title: str, owner: str | None = None, shared: bool = True) -> str:
    song_id = storage.new_id()
    storage.create_song(
        song_id=song_id,
        title=title,
        artist="",
        filename=f"{song_id}.mp3",
        original_name=f"{title}.mp3",
        content_type="audio/mpeg",
        size_bytes=1,
        owner_id=owner,
        shared=shared,
    )
    return song_id


def titles(viewer: str | None) -> set[str]:
    return {song["title"] for song in storage.list_songs(viewer_id=viewer)}


class TestWithoutAccounts:
    def test_everything_is_listed_when_nobody_is_signed_in(self, db):
        add("aberta")
        add("de alguem", owner="user-1")
        add("privada", owner="user-1", shared=False)
        assert titles(None) == {"aberta", "de alguem", "privada"}

    def test_songs_are_shared_by_default(self, db):
        add("nova")
        assert storage.list_songs()[0]["shared"] is True


class TestWithAccounts:
    def test_you_see_your_own(self, db):
        add("minha", owner="user-1", shared=False)
        assert titles("user-1") == {"minha"}

    def test_you_see_what_others_shared(self, db):
        add("do outro", owner="user-2", shared=True)
        assert titles("user-1") == {"do outro"}

    def test_you_do_not_see_what_others_kept_private(self, db):
        add("segredo do outro", owner="user-2", shared=False)
        assert titles("user-1") == set()

    def test_songs_from_before_accounts_stay_visible_to_everyone(self, db):
        # Songs are different from setlists: the library is the house's, so an
        # unclaimed song stays visible until somebody makes it private. What
        # must not happen is it vanishing the moment a login is enabled.
        add("antiga", owner=None)
        assert titles("user-1") == {"antiga"}
        assert titles("user-2") == {"antiga"}

    def test_your_own_private_song_is_still_yours_to_see(self, db):
        add("minha privada", owner="user-1", shared=False)
        add("do outro privada", owner="user-2", shared=False)
        assert titles("user-1") == {"minha privada"}

    def test_sharing_can_be_turned_off_and_on(self, db):
        song = add("minha", owner="user-1", shared=True)
        storage.set_song_sharing(song, False)
        assert titles("user-2") == set()
        storage.set_song_sharing(song, True)
        assert titles("user-2") == {"minha"}

    def test_search_still_applies_within_what_you_may_see(self, db):
        add("bebendo", owner="user-1")
        add("outra", owner="user-1")
        found = storage.list_songs(search="beb", viewer_id="user-1")
        assert [song["title"] for song in found] == ["bebendo"]


class TestSetlists:
    def test_a_set_is_private_to_its_owner(self, db):
        # A running order is personal: two people playing the same songs on
        # different nights each want their own.
        storage.create_setlist("meu show", owner_id="user-1")
        assert [item["name"] for item in storage.list_setlists("user-1")] == ["meu show"]
        assert storage.list_setlists("user-2") == []

    def test_a_set_with_no_owner_is_not_everybody_s(self, db):
        # It used to be, on the same "belongs to the house" reasoning that is
        # right for the music library — and one person's running order turned
        # up in another person's account. A set is personal; an unclaimed one
        # is nobody's until it is adopted.
        storage.create_setlist("antigo", owner_id=None)
        assert storage.list_setlists("user-1") == []
        assert storage.list_setlists("user-2") == []

    def test_the_first_account_adopts_what_predates_accounts(self, db):
        storage.create_setlist("antigo", owner_id=None)
        song = add("antiga", owner=None)
        songs, sets = storage.adopt_orphans("user-1")

        assert (songs, sets) == (1, 1)
        assert [item["name"] for item in storage.list_setlists("user-1")] == ["antigo"]
        assert storage.list_setlists("user-2") == []
        assert storage.get_song(song)["ownerId"] == "user-1"

    def test_adoption_leaves_things_that_already_have_an_owner_alone(self, db):
        storage.create_setlist("da adriana", owner_id="user-2")
        storage.adopt_orphans("user-1")
        assert [item["name"] for item in storage.list_setlists("user-2")] == ["da adriana"]
        assert storage.list_setlists("user-1") == []

    def test_without_accounts_every_set_is_listed(self, db):
        storage.create_setlist("um", owner_id="user-1")
        storage.create_setlist("dois", owner_id="user-2")
        assert len(storage.list_setlists(None)) == 2
