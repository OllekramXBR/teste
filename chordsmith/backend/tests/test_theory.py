from app.analysis import theory
from app.analysis.theory import Chord


def test_chord_pitch_classes():
    assert Chord(7, "").pitch_classes() == (7, 11, 2)  # G B D
    assert Chord(4, "m").pitch_classes() == (4, 7, 11)  # E G B
    assert Chord(0, "maj7").pitch_classes() == (0, 4, 7, 11)  # C E G B


def test_labels_follow_the_key_signature():
    assert Chord(6, "").label(use_flats=False) == "F#"
    assert Chord(6, "").label(use_flats=True) == "Gb"
    assert Chord(10, "m7").label(use_flats=True) == "Bbm7"


def test_parse_label_round_trips():
    for label in ("G", "Em", "F#m7", "Bbmaj7", "C#dim", "Absus4"):
        chord = theory.parse_label(label)
        assert chord is not None, label
        assert chord.label(use_flats="b" in label[:2]) == label


def test_parse_label_rejects_unknown_quality():
    assert theory.parse_label("Cfoo") is None


def test_transposition_wraps_the_octave():
    assert theory.transpose_label("A", 3) == "C"
    assert theory.transpose_label("C", -1) == "B"
    assert theory.transpose_label("Em", 12) == "Em"


def test_capo_shapes_are_the_written_chords_moved_down():
    # With a capo on 2, playing G/D/Em/C shapes sounds as A/E/F#m/D.
    sounding = ["A", "E", "F#m", "D"]
    assert theory.capo_shift(sounding, 2) == ["G", "D", "Em", "C"]


def test_capo_zero_changes_nothing():
    labels = ["G", "D", "Em", "C"]
    assert theory.capo_shift(labels, 0) == labels


def test_key_spelling_conventions():
    assert theory.key_uses_flats(5, "major") is True  # F major
    assert theory.key_uses_flats(7, "major") is False  # G major
    assert theory.key_name(7, "major") == "G major"
    assert theory.key_name(10, "major") == "Bb major"


def test_chord_fits_key():
    assert theory.chord_fits_key(Chord(4, "m"), 7, "major") is True  # Em in G
    assert theory.chord_fits_key(Chord(4, ""), 7, "major") is False  # E major is not


def test_vocabulary_covers_every_root_and_quality():
    vocabulary = theory.chord_vocabulary()
    assert vocabulary[0].is_none
    assert len(vocabulary) == 12 * len(theory.QUALITIES) + 1
