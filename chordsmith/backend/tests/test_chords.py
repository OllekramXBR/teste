import numpy as np

from app.analysis import chords, theory


def chroma_for(root: int, quality: str, strength: float = 1.0) -> np.ndarray:
    vector = np.zeros(12, dtype=np.float32)
    for interval in theory.QUALITIES[quality]:
        vector[(root + interval) % 12] = strength
    return vector


def test_templates_are_unit_length():
    templates, vocabulary, _ = chords.build_templates()
    assert templates.shape == (len(vocabulary), 12)
    norms = np.linalg.norm(templates, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_emission_prefers_the_matching_chord():
    chroma = np.column_stack([chroma_for(7, ""), chroma_for(4, "m")])
    scores, vocabulary = chords.emission_scores(chroma)
    assert vocabulary[int(np.argmax(scores[0]))] == theory.Chord(7, "")
    assert vocabulary[int(np.argmax(scores[1]))] == theory.Chord(4, "m")


def test_silence_decodes_as_no_chord():
    chroma = np.column_stack([chroma_for(0, ""), np.zeros(12), chroma_for(0, "")])
    sequence, _, _ = chords.decode(chroma)
    assert sequence[1].is_none


def test_viterbi_smooths_an_ambiguous_beat():
    # Ten beats of C with one ambiguous beat in the middle, half C and half F#.
    # The emission alone cannot choose between them, so the transition prior is
    # what has to hold the line. (A beat that unambiguously spells out F# is not
    # noise to smooth away — it really is an F#, and the decoder should say so.)
    ambiguous = chroma_for(0, "") + chroma_for(6, "")
    columns = [chroma_for(0, "")] * 5 + [ambiguous] + [chroma_for(0, "")] * 5
    sequence, _, _ = chords.decode(np.column_stack(columns))
    assert all(chord == theory.Chord(0, "") for chord in sequence)


def test_viterbi_still_follows_a_real_change():
    columns = [chroma_for(0, "")] * 6 + [chroma_for(5, "")] * 6
    sequence, _, _ = chords.decode(np.column_stack(columns))
    assert sequence[0] == theory.Chord(0, "")
    assert sequence[-1] == theory.Chord(5, "")


def test_viterbi_handles_an_empty_sequence():
    assert chords.viterbi(np.zeros((0, 5))).shape == (0,)


def test_key_estimation_finds_the_tonic():
    # A cadence that spells out G major.
    columns = [chroma_for(7, ""), chroma_for(0, ""), chroma_for(2, ""), chroma_for(4, "m")] * 4
    tonic, mode, confidence = chords.estimate_key(np.column_stack(columns))
    assert tonic == 7
    assert mode == "major"
    assert confidence > 0


def test_key_estimation_on_silence_is_not_confident():
    tonic, mode, confidence = chords.estimate_key(np.zeros((12, 8)))
    assert (tonic, mode, confidence) == (0, "major", 0.0)


def test_bass_chroma_disambiguates_the_root():
    # A minor and C major share two notes; the bass decides which it is.
    chroma = np.column_stack([chroma_for(9, "m")])
    bass = np.zeros((12, 1), dtype=np.float32)
    bass[9] = 1.0
    scores, vocabulary = chords.emission_scores(chroma, bass)
    assert vocabulary[int(np.argmax(scores[0]))].root == 9
