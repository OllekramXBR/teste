"""Lead transcription against a track with a known melodic section."""

from __future__ import annotations

import numpy as np

from app.analysis import melody
from app.analysis.melody import Note


def test_lead_notes_are_found_in_the_second_half(lead_analysis):
    notes = lead_analysis.tab_notes
    assert len(notes) > 20
    late = [note for note in notes if note.note.start >= 19.0]
    assert len(late) > len(notes) * 0.6, "the lead only plays over the second half"


def test_detected_pitches_sit_in_the_lead_register(lead_analysis):
    late = [note.note.midi for note in lead_analysis.tab_notes if note.note.start >= 19.0]
    # The written line spans G4-G5; allow the odd octave slip below it.
    assert min(late) >= 48
    assert max(late) <= 84


def test_a_solo_section_is_flagged(lead_analysis):
    solos = [section for section in lead_analysis.lead_sections if section.is_solo]
    assert solos, "the eighth-note lead should read as a solo"
    assert solos[0].start >= 15.0
    assert solos[0].notes_per_bar >= melody.SOLO_NOTES_PER_BAR


def test_chords_only_track_has_no_solo(chord_analysis):
    assert not any(section.is_solo for section in chord_analysis.lead_sections)


def test_every_note_maps_to_a_reachable_fret(lead_analysis):
    from app.analysis.tab import GUITAR_TUNING

    for entry in lead_analysis.tab_notes:
        if entry.string is None or entry.fret is None:
            continue
        assert GUITAR_TUNING[entry.string] + entry.fret == entry.note.midi


def test_notes_do_not_overlap(lead_analysis):
    starts = [entry.note.start for entry in lead_analysis.tab_notes]
    assert starts == sorted(starts)


def test_octave_correction_pulls_back_a_lone_outlier():
    line = [Note(i * 0.5, i * 0.5 + 0.4, pitch, 0.9, 0.5) for i, pitch in enumerate([67, 69, 59, 71, 72])]
    melody._correct_octaves(line)
    assert line[2].midi == 71  # 59 was an octave below the surrounding line


def test_octave_correction_leaves_a_genuine_leap_alone():
    line = [Note(i * 0.5, i * 0.5 + 0.4, pitch, 0.9, 0.5) for i, pitch in enumerate([60, 62, 64, 65, 67])]
    before = [note.midi for note in line]
    melody._correct_octaves(line)
    assert [note.midi for note in line] == before


def test_segmentation_splits_a_repeated_note_on_its_onset():
    frames = 60
    midi = np.full(frames, 67.0)
    voiced = np.full(frames, 0.9)
    times = np.arange(frames) * 0.0232
    rms = np.full(frames, 0.5)

    without = melody.segment_notes(midi, voiced, times, rms)
    with_onset = melody.segment_notes(midi, voiced, times, rms, np.array([30]))
    assert len(without) == 1
    assert len(with_onset) == 2


def test_silence_yields_no_notes():
    frames = 40
    assert (
        melody.segment_notes(
            np.full(frames, np.nan),
            np.zeros(frames),
            np.arange(frames) * 0.0232,
            np.zeros(frames),
        )
        == []
    )
