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
