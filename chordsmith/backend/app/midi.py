"""Minimal Standard MIDI File writer for chord charts.

Writes a format-1 file with two tracks: a tempo/meta track and a chord track.
Everything is emitted as raw bytes, so there is no MIDI dependency to install.
"""

from __future__ import annotations

import struct
from typing import Iterable, Sequence

TICKS_PER_BEAT = 480

# Voicing range for the rendered chords: roughly the middle of a piano, where
# block chords sound closest to how a guitarist would strum them.
BASS_OCTAVE = 36  # C2
CHORD_OCTAVE = 60  # C4


def _variable_length(value: int) -> bytes:
    """MIDI variable-length quantity encoding."""
    if value < 0:
        raise ValueError("variable-length quantities must be non-negative")
    buffer = value & 0x7F
    chunks = [buffer]
    value >>= 7
    while value:
        chunks.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(chunks))


def _event(delta: int, data: bytes) -> bytes:
    return _variable_length(delta) + data


def _track_chunk(events: bytes) -> bytes:
    body = events + _event(0, b"\xff\x2f\x00")  # end of track
    return b"MTrk" + struct.pack(">I", len(body)) + body


def _voice_chord(root: int, intervals: Sequence[int]) -> list[int]:
    """Lay a chord out as a bass note plus a close voicing above middle C."""
    notes = [BASS_OCTAVE + root]
    previous = CHORD_OCTAVE + root
    notes.append(previous)
    for interval in intervals[1:]:
        pitch = CHORD_OCTAVE + root + interval
        while pitch <= previous:
            pitch += 12
        notes.append(pitch)
        previous = pitch
    return [n for n in notes if 0 <= n <= 127]


def build_midi(
    chords: Iterable[dict],
    bpm: float,
    beats_per_bar: int = 4,
    transpose: int = 0,
    title: str = "Chord chart",
) -> bytes:
    """Render a chord chart to MIDI bytes.

    ``chords`` items need ``root``, ``quality``/``notes``, ``startBeat`` and
    ``endBeat``; timing is taken from the beat grid rather than the wall clock so
    the export lines up with a DAW's bars.
    """
    tempo = max(int(round(60_000_000 / bpm)), 1) if bpm and bpm > 0 else 500_000

    meta = b""
    meta += _event(0, b"\xff\x03" + _variable_length(len(title.encode())) + title.encode())
    meta += _event(0, b"\xff\x51\x03" + struct.pack(">I", tempo)[1:])
    denominator_power = 2  # quarter-note beats
    meta += _event(0, bytes([0xFF, 0x58, 0x04, beats_per_bar, denominator_power, 24, 8]))

    track = b""
    cursor = 0  # position in ticks where the last event was written
    for chord in chords:
        root = chord.get("root")
        start_beat = int(chord.get("startBeat", 0))
        end_beat = int(chord.get("endBeat", start_beat))
        start_tick = start_beat * TICKS_PER_BEAT
        length = max((end_beat - start_beat + 1) * TICKS_PER_BEAT, TICKS_PER_BEAT // 2)

        if root is None:
            continue

        intervals = [(n - root) % 12 for n in chord.get("notes", [])] or [0, 4, 7]
        intervals = sorted(set(intervals))
        pitches = _voice_chord((root + transpose) % 12, intervals)

        for index, pitch in enumerate(pitches):
            delta = start_tick - cursor if index == 0 else 0
            track += _event(max(delta, 0), bytes([0x90, pitch, 80]))
            cursor = max(cursor, start_tick)

        release = start_tick + length - int(TICKS_PER_BEAT * 0.1)
        for index, pitch in enumerate(pitches):
            delta = release - cursor if index == 0 else 0
            track += _event(max(delta, 0), bytes([0x80, pitch, 0]))
            cursor = max(cursor, release)

    header = b"MThd" + struct.pack(">IHHH", 6, 1, 2, TICKS_PER_BEAT)
    return header + _track_chunk(meta) + _track_chunk(track)


def _note_track(
    notes: Iterable[dict], bpm: float, channel: int, program: int, name: str, transpose: int
) -> bytes:
    """One monophonic line as its own MIDI track.

    Timing comes from the note's own seconds rather than the beat grid, because
    these were transcribed from audio and a bass player who pushes the beat
    should still land where they played, not where the grid says they should
    have.
    """
    ticks_per_second = (bpm / 60.0) * TICKS_PER_BEAT if bpm > 0 else 2.0 * TICKS_PER_BEAT

    events = b""
    events += _event(0, b"\xff\x03" + _variable_length(len(name.encode())) + name.encode())
    events += _event(0, bytes([0xC0 | channel, program]))

    cursor = 0
    for note in sorted(notes, key=lambda item: item["start"]):
        pitch = int(round(note["midi"])) + transpose
        if not 0 <= pitch <= 127:
            continue
        start = int(round(note["start"] * ticks_per_second))
        end = max(int(round(note["end"] * ticks_per_second)), start + TICKS_PER_BEAT // 8)
        velocity = max(1, min(127, int(round(note.get("velocity", 0.7) * 127))))

        # A monophonic line: the previous note is always released before the
        # next begins, which a transcription cannot guarantee on its own.
        start = max(start, cursor)
        events += _event(max(start - cursor, 0), bytes([0x90 | channel, pitch, velocity]))
        cursor = start
        events += _event(max(end - cursor, 0), bytes([0x80 | channel, pitch, 0]))
        cursor = end

    return _track_chunk(events)


def build_multitrack(
    chords: Iterable[dict],
    tracks: Iterable[dict],
    bpm: float,
    beats_per_bar: int = 4,
    transpose: int = 0,
    title: str = "Chart",
) -> bytes:
    """Chords plus one track per transcribed stem.

    Each part gets its own channel and instrument, so opening the file in a DAW
    gives separate, editable lines instead of one merged blur — which is the
    entire reason to want a multitrack export rather than a chord chart.
    """
    tempo = max(int(round(60_000_000 / bpm)), 1) if bpm and bpm > 0 else 500_000

    meta = b""
    meta += _event(0, b"\xff\x03" + _variable_length(len(title.encode())) + title.encode())
    meta += _event(0, b"\xff\x51\x03" + struct.pack(">I", tempo)[1:])
    meta += _event(0, bytes([0xFF, 0x58, 0x04, beats_per_bar, 2, 24, 8]))

    # The chord track is built by the existing writer and its bytes reused, so
    # the two exports cannot drift apart in how they voice a chord.
    chord_chunk = build_midi(chords, bpm, beats_per_bar, transpose, title)
    chord_track = chord_chunk[chord_chunk.index(b"MTrk", 14 + 8) :]

    chunks = [chord_track]
    for index, track in enumerate(tracks):
        # Channel 9 is percussion in General MIDI; skipping it keeps a bass line
        # from being played as a snare drum.
        channel = index + 1 if index + 1 < 9 else index + 2
        chunks.append(
            _note_track(
                track["notes"],
                bpm,
                channel=min(channel, 15),
                program=int(track.get("program", 0)),
                name=str(track.get("name", f"Track {index + 1}")),
                transpose=transpose,
            )
        )

    header = b"MThd" + struct.pack(">IHHH", 6, 1, 1 + len(chunks), TICKS_PER_BEAT)
    return header + _track_chunk(meta) + b"".join(chunks)
