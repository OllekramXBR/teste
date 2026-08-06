"""Tests for browsing the server's own audio library.

Most of these are about one thing: a path that arrives from a client must never
reach anything outside the configured root. That check is the entire security
model of the feature, so it is tested against traversal written longhand,
against absolute paths, and against a symlink pointing out of the share — which
is the case a naive string comparison would let through.
"""

from __future__ import annotations

import pytest

from app import library


@pytest.fixture
def root(tmp_path, monkeypatch):
    music = tmp_path / "music"
    (music / "Album").mkdir(parents=True)
    (music / "song.mp3").write_bytes(b"x" * 32)
    (music / "Album" / "track.flac").write_bytes(b"x" * 32)
    (music / "Album" / "cover.jpg").write_bytes(b"x" * 32)
    (music / "notes.txt").write_text("not audio")
    (music / "empty.mp3").write_bytes(b"")
    (tmp_path / "secret.mp3").write_bytes(b"x" * 32)
    monkeypatch.setattr(library, "LIBRARY_ROOT", music)
    return tmp_path


class TestConfinement:
    @pytest.mark.parametrize(
        "attempt",
        ["../secret.mp3", "Album/../../secret.mp3", "/etc/passwd", "../../../../etc/passwd"],
    )
    def test_paths_outside_the_root_are_refused(self, root, attempt):
        with pytest.raises(library.LibraryError):
            library.resolve(attempt)

    def test_a_symlink_pointing_out_of_the_share_is_refused(self, root):
        # The case a string comparison misses: the path looks like it is inside
        # the library right up until the filesystem follows it.
        link = library.LIBRARY_ROOT / "escape.mp3"
        try:
            link.symlink_to(root / "secret.mp3")
        except OSError:
            pytest.skip("this filesystem does not allow symlinks")
        with pytest.raises(library.LibraryError):
            library.resolve("escape.mp3")

    def test_the_root_itself_is_allowed(self, root):
        assert library.resolve("") == library.LIBRARY_ROOT

    def test_a_path_that_does_not_exist_is_refused(self, root):
        with pytest.raises(library.LibraryError):
            library.resolve("nope.mp3")


class TestListing:
    def test_folders_come_before_files(self, root):
        _, entries = library.listing("")
        assert entries[0].is_dir is True
        assert entries[0].name == "Album"

    def test_only_playable_files_are_listed(self, root):
        _, entries = library.listing("Album")
        assert [entry.name for entry in entries] == ["track.flac"]

    def test_non_audio_files_are_left_out_of_the_root_too(self, root):
        _, entries = library.listing("")
        assert "notes.txt" not in [entry.name for entry in entries]

    def test_entries_carry_a_path_the_client_can_send_back(self, root):
        _, entries = library.listing("Album")
        assert entries[0].path == "Album/track.flac"
        assert library.resolve(entries[0].path).name == "track.flac"

    def test_file_sizes_are_reported(self, root):
        _, entries = library.listing("")
        song = next(entry for entry in entries if entry.name == "song.mp3")
        assert song.bytes == 32

    def test_listing_a_file_rather_than_a_folder_is_an_error(self, root):
        with pytest.raises(library.LibraryError):
            library.listing("song.mp3")


class TestImportCandidates:
    def test_a_playable_file_is_accepted(self, root):
        assert library.audio_file("song.mp3").name == "song.mp3"

    def test_a_folder_is_refused(self, root):
        with pytest.raises(library.LibraryError):
            library.audio_file("Album")

    def test_an_unsupported_format_is_refused(self, root):
        with pytest.raises(library.LibraryError):
            library.audio_file("notes.txt")

    def test_an_empty_file_is_refused_before_anything_copies_it(self, root):
        with pytest.raises(library.LibraryError):
            library.audio_file("empty.mp3")

    def test_traversal_is_refused_at_import_too(self, root):
        # Not only at listing time: this is the entry point that copies bytes.
        with pytest.raises(library.LibraryError):
            library.audio_file("../secret.mp3")


class TestDisabled:
    def test_nothing_is_reachable_when_no_library_is_configured(self, monkeypatch):
        monkeypatch.setattr(library, "LIBRARY_ROOT", None)
        assert library.enabled() is False
        with pytest.raises(library.LibraryError):
            library.resolve("")
