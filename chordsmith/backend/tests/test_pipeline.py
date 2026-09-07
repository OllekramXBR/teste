"""End-to-end analysis against a synthetic track whose chords are known."""

from __future__ import annotations

import pytest

from .conftest import EXPECTED_LABELS


def test_tempo_and_meter(chord_analysis):
    assert chord_analysis.bpm == pytest.approx(100, abs=3)
    assert chord_analysis.beats_per_bar == 4


def test_key_detection(chord_analysis):
    assert (chord_analysis.key_tonic, chord_analysis.key_mode) == (7, "major")


def test_beat_grid_covers_the_track(chord_analysis):
    beats = chord_analysis.beat_events
    assert len(beats) > 50
    assert beats[0].time < 1.0
    assert beats[-1].time < chord_analysis.duration
    # Beats must be strictly increasing, or the player's lookup breaks.
    assert all(later.time > earlier.time for earlier, later in zip(beats, beats[1:]))


def test_downbeats_land_every_four_beats(chord_analysis):
    downbeats = [beat.index for beat in chord_analysis.beat_events if beat.downbeat]
    assert len(downbeats) >= 8
    gaps = {later - earlier for earlier, later in zip(downbeats, downbeats[1:])}
    assert gaps == {4}


def test_progression_is_recovered(chord_analysis):
    labels = [span.chord.label() for span in chord_analysis.spans if not span.chord.is_none]
    # The tail of the file is silence, so compare only as far as the source goes.
    assert labels[: len(EXPECTED_LABELS)] == EXPECTED_LABELS


def test_spans_are_contiguous_and_ordered(chord_analysis):
    spans = chord_analysis.spans
    assert all(span.end > span.start for span in spans)
    assert all(
        later.start >= earlier.start for earlier, later in zip(spans, spans[1:])
    )


def test_serialised_shape(chord_analysis):
    payload = chord_analysis.to_dict()
    assert payload["key"]["name"] == "G major"
    assert payload["beatsPerBar"] == 4
    assert set(payload["uniqueChords"]) >= {"G", "D", "Em", "C"}
    first = payload["beats"][0]
    assert set(first) >= {"index", "time", "bar", "beatInBar", "downbeat", "label"}
    assert "lead" in payload and "notes" in payload["lead"]


def test_short_input_is_handled(tmp_path):
    import numpy as np
    import soundfile as sf

    from app.analysis.pipeline import analyze_file

    path = tmp_path / "blip.wav"
    sf.write(path, np.zeros(1000, dtype="float32"), 22050)
    result = analyze_file(path)
    assert result.beat_events == []
    assert result.to_dict()["bpm"] == 0
