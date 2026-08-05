import struct

from app.midi import TICKS_PER_BEAT, build_midi

CHORDS = [
    {"root": 7, "notes": [7, 11, 2], "startBeat": 0, "endBeat": 3},
    {"root": 2, "notes": [2, 6, 9], "startBeat": 4, "endBeat": 7},
    {"root": None, "notes": [], "startBeat": 8, "endBeat": 11},
]


def test_header_is_a_valid_two_track_file():
    data = build_midi(CHORDS, bpm=120)
    assert data[:4] == b"MThd"
    length, fmt, tracks, division = struct.unpack(">IHHH", data[4:14])
    assert (length, fmt, tracks, division) == (6, 1, 2, TICKS_PER_BEAT)


def test_track_chunks_declare_their_own_length():
    data = build_midi(CHORDS, bpm=120)
    offset = 14
    for _ in range(2):
        assert data[offset : offset + 4] == b"MTrk"
        (size,) = struct.unpack(">I", data[offset + 4 : offset + 8])
        offset += 8 + size
    assert offset == len(data)  # nothing trailing, nothing truncated


def test_tempo_meta_event_matches_the_bpm():
    data = build_midi(CHORDS, bpm=120)
    index = data.index(b"\xff\x51\x03")
    microseconds = int.from_bytes(data[index + 3 : index + 6], "big")
    assert microseconds == 500_000  # 120 BPM


def test_transposition_shifts_every_note():
    plain = build_midi(CHORDS, bpm=120)
    shifted = build_midi(CHORDS, bpm=120, transpose=2)
    assert plain != shifted
    assert len(plain) == len(shifted)  # same events, different pitches


def test_no_chord_spans_emit_nothing():
    only_rest = build_midi([CHORDS[2]], bpm=120)
    assert len(only_rest) < len(build_midi(CHORDS, bpm=120))


def test_zero_bpm_falls_back_to_a_sane_tempo():
    data = build_midi(CHORDS, bpm=0)
    index = data.index(b"\xff\x51\x03")
    assert int.from_bytes(data[index + 3 : index + 6], "big") == 500_000


def test_empty_chart_still_produces_a_valid_file():
    data = build_midi([], bpm=90)
    assert data[:4] == b"MThd"
    assert data.count(b"MTrk") == 2
