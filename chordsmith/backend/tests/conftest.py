"""Shared fixtures: a synthetic track with a known chord progression."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SR = 22050
BPM = 100
BEAT = 60 / BPM

# I-V-vi-IV in G major, one bar each, repeated. This is the ground truth the
# analysis tests assert against.
PROGRESSION = [(7, "maj"), (2, "maj"), (4, "min"), (0, "maj")] * 4
EXPECTED_LABELS = ["G", "D", "Em", "C"] * 4


def _midi_to_hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _render(with_lead: bool) -> np.ndarray:
    rng = np.random.default_rng(0)
    total = int(SR * BEAT * 4 * len(PROGRESSION)) + SR
    out = np.zeros(total)

    position = 0
    for root, quality in PROGRESSION:
        length = int(SR * BEAT * 4)
        t = np.arange(length) / SR
        segment = np.zeros(length)
        intervals = [0, 4, 7] if quality == "maj" else [0, 3, 7]

        segment += 0.30 * np.sin(2 * np.pi * _midi_to_hz(48 + root) * t)
        for interval in intervals:
            for harmonic, amplitude in ((1, 0.16), (2, 0.06)):
                segment += amplitude * np.sin(
                    2 * np.pi * _midi_to_hz(60 + root + interval) * harmonic * t
                )

        envelope = np.ones(length)
        for beat in range(4):
            start, end = int(beat * BEAT * SR), int((beat + 1) * BEAT * SR)
            envelope[start:end] = np.exp(-3.0 * np.arange(end - start) / SR)

        out[position : position + length] += segment * envelope
        position += length

    if with_lead:
        # An eighth-note line over the second half, inside the G major scale.
        scale = [67, 69, 71, 72, 74, 76, 78, 79]
        for index in range(64):
            midi = scale[index % len(scale)]
            start = int((32 + index * 0.5) * BEAT * SR)
            length = int(0.42 * BEAT * SR)
            if start + length > total:
                break
            t = np.arange(length) / SR
            tone = (
                0.50 * np.sin(2 * np.pi * _midi_to_hz(midi) * t)
                + 0.18 * np.sin(2 * np.pi * _midi_to_hz(midi) * 2 * t)
                + 0.07 * np.sin(2 * np.pi * _midi_to_hz(midi) * 3 * t)
            )
            attack = int(0.005 * SR)
            envelope = np.concatenate(
                [np.linspace(0, 1, attack), np.exp(-2.2 * np.arange(length - attack) / SR)]
            )
            out[start : start + length] += tone * envelope

    # Click track, accented on the downbeat, so beat tracking has something to
    # lock onto the way a real drum part would provide.
    for beat in range(int(total / SR / BEAT)):
        start, length = int(beat * BEAT * SR), int(0.04 * SR)
        if start + length > total:
            break
        click = rng.standard_normal(length) * np.exp(-40 * np.arange(length) / SR)
        out[start : start + length] += (0.45 if beat % 4 == 0 else 0.20) * click

    return (out / (np.max(np.abs(out)) * 1.05)).astype(np.float32)


@pytest.fixture(scope="session")
def chord_track(tmp_path_factory) -> Path:
    """A 39-second I-V-vi-IV loop in G major at 100 BPM."""
    path = tmp_path_factory.mktemp("audio") / "chords.wav"
    sf.write(path, _render(with_lead=False), SR)
    return path


@pytest.fixture(scope="session")
def lead_track(tmp_path_factory) -> Path:
    """The same loop with an eighth-note lead over its second half."""
    path = tmp_path_factory.mktemp("audio") / "lead.wav"
    sf.write(path, _render(with_lead=True), SR)
    return path


@pytest.fixture(scope="session")
def chord_analysis(chord_track):
    from app.analysis.pipeline import analyze_file

    return analyze_file(chord_track)


@pytest.fixture(scope="session")
def lead_analysis(lead_track):
    from app.analysis.pipeline import analyze_file

    return analyze_file(lead_track)
