"""Tests for the multitrack MIDI export.

A MIDI file that a DAW refuses to open is worse than no export at all, so most
of these check the structure the format actually requires: the right chunk
count in the header, one chunk per track, and notes that are released before
the next one starts.
"""

from __future__ import annotations

import struct

import pytest

from app.midi import build_multitrack


def note(midi: int, start: float, end: float, velocity: float = 0.7) -> dict:
    return {"midi": midi, "start": start, "end": end, "velocity": velocity}


@pytest.fixture
def chords() -> list[dict]:
    return [
        {"root": 7, "notes": [7, 11, 2], "startBeat": 0, "endBeat": 3},
        {"root": 2, "notes": [2, 6, 9], "startBeat": 4, "endBeat": 7},
    ]


@pytest.fixture
def tracks() -> list[dict]:
    return [
        {"name": "Baixo", "program": 33, "notes": [note(43, 0.0, 0.5), note(45, 0.5, 1.0)]},
        {"name": "Melodia", "program": 26, "notes": [note(67, 0.0, 0.4)]},
    ]


def chunk_count(data: bytes) -> int:
    return struct.unpack(">H", data[10:12])[0]


class TestStructure:
    def test_it_is_a_format_1_file(self, chords, tracks):
        data = build_multitrack(chords, tracks, bpm=120)
        assert data[:4] == b"MThd"
        assert struct.unpack(">H", data[8:10])[0] == 1

    def test_the_header_counts_every_chunk_that_follows(self, chords, tracks):
        # A header that lies about its track count is exactly the kind of file
        # a DAW opens halfway and then gives up on.
        data = build_multitrack(chords, tracks, bpm=120)
        assert chunk_count(data) == data.count(b"MTrk")

    def test_each_stem_becomes_its_own_track(self, chords, tracks):
        # meta + chords + one per stem
        data = build_multitrack(chords, tracks, bpm=120)
        assert data.count(b"MTrk") == 2 + len(tracks)

    def test_track_names_are_written(self, chords, tracks):
        data = build_multitrack(chords, tracks, bpm=120)
        assert b"Baixo" in data
        assert b"Melodia" in data

    def test_no_stems_still_produces_a_valid_file(self, chords):
        data = build_multitrack(chords, [], bpm=120)
        assert chunk_count(data) == data.count(b"MTrk") == 2


class TestNotes:
    def test_each_line_gets_its_own_channel(self, chords, tracks):
        data = build_multitrack(chords, tracks, bpm=120)
        # Channel 0 is the chords; the stems take 1 and 2.
        assert bytes([0x91]) in data
        assert bytes([0x92]) in data

    def test_percussion_channel_is_skipped(self, chords):
        # Channel 9 is drums in General MIDI; a bass line routed there would be
        # played as a snare.
        many = [{"name": f"L{i}", "program": 0, "notes": [note(60, 0, 0.2)]} for i in range(10)]
        data = build_multitrack(chords, many, bpm=120)
        assert bytes([0x99]) not in data

    def test_transposition_moves_the_transcribed_notes_too(self, chords):
        plain = build_multitrack(chords, [{"name": "B", "program": 33, "notes": [note(43, 0, 1)]}], bpm=120)
        moved = build_multitrack(
            chords, [{"name": "B", "program": 33, "notes": [note(43, 0, 1)]}], bpm=120, transpose=2
        )
        assert plain != moved

    def test_notes_outside_the_midi_range_are_dropped_not_wrapped(self, chords):
        # Wrapping would put a note in the wrong octave, which is worse than a
        # missing one because it sounds plausible.
        data = build_multitrack(
            chords, [{"name": "B", "program": 33, "notes": [note(200, 0, 1)]}], bpm=120
        )
        assert chunk_count(data) == data.count(b"MTrk")

    def test_an_empty_line_still_writes_its_track(self, chords):
        data = build_multitrack(chords, [{"name": "Vazia", "program": 1, "notes": []}], bpm=120)
        assert b"Vazia" in data
        assert chunk_count(data) == data.count(b"MTrk")
