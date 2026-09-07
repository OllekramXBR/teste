"""Chord recognition: beat-synchronous chroma -> smoothed chord sequence.

The decoder is a first-order hidden Markov model over the chord vocabulary in
:mod:`theory`. Emission scores come from cosine similarity between the observed
chroma and a weighted binary template per chord; transitions prefer staying on
the current chord, which is what turns a noisy frame-wise guess into the stable,
bar-aligned sequence a player can actually read.
"""

from __future__ import annotations

import numpy as np

from . import theory
from .theory import Chord, chord_vocabulary

# Emission sharpness. Cosine similarities live in a narrow band, so they are
# scaled before entering the log domain or the transition prior swamps them.
EMISSION_SCALE = 11.0

# Log-probability bonus for staying on the same chord between two beats.
SELF_TRANSITION_BONUS = 2.6

# How strongly a chord is favoured for belonging to the estimated key.
KEY_BONUS = 0.35

# Chroma energy below this fraction of the median is treated as "no chord".
SILENCE_RATIO = 0.18


def build_templates() -> tuple[np.ndarray, list[Chord], np.ndarray]:
    """Return the unit-norm template matrix, its chord vocabulary and priors.

    The template matrix has shape ``(n_chords, 12)``. Row 0 is the "no chord"
    template: a flat vector, which correlates equally with everything and only
    wins when the observation itself is flat.
    """
    vocab = chord_vocabulary()
    templates = np.zeros((len(vocab), 12), dtype=np.float32)
    priors = np.zeros(len(vocab), dtype=np.float32)

    templates[0, :] = 1.0 / np.sqrt(12.0)
    priors[0] = 0.0

    for index, chord in enumerate(vocab[1:], start=1):
        vector = np.zeros(12, dtype=np.float32)
        for interval in chord.intervals():
            vector[(chord.root + interval) % 12] = theory.INTERVAL_WEIGHTS.get(interval, 0.8)
        templates[index] = vector / np.linalg.norm(vector)
        priors[index] = theory.QUALITY_PRIOR[chord.quality]

    return templates, vocab, priors


def emission_scores(
    chroma: np.ndarray,
    bass_chroma: np.ndarray | None = None,
    key: tuple[int, str] | None = None,
) -> tuple[np.ndarray, list[Chord]]:
    """Score every chord against every beat.

    ``chroma`` and ``bass_chroma`` are ``(12, n_beats)`` matrices. The bass
    chroma is folded in as a root bonus: the lowest sounding pitch class is the
    single strongest cue for the root, and plain full-range chroma tends to lose
    it among the upper partials.
    """
    templates, vocab, priors = build_templates()

    frames = chroma.T.astype(np.float32)  # (n_beats, 12)
    norms = np.linalg.norm(frames, axis=1, keepdims=True)
    energy = norms[:, 0].copy()
    normalized = frames / np.maximum(norms, 1e-8)

    scores = normalized @ templates.T  # cosine similarity, (n_beats, n_chords)
    scores = scores * EMISSION_SCALE + priors[np.newaxis, :]

    if bass_chroma is not None and bass_chroma.size:
        bass = bass_chroma.T.astype(np.float32)
        bass = bass / np.maximum(np.linalg.norm(bass, axis=1, keepdims=True), 1e-8)
        root_of = np.array([-1 if c.root is None else c.root for c in vocab])
        has_root = root_of >= 0
        root_strength = np.zeros_like(scores)
        root_strength[:, has_root] = bass[:, root_of[has_root]]
        scores += 2.2 * root_strength

    if key is not None:
        tonic, mode = key
        in_key = np.array(
            [theory.chord_fits_key(c, tonic, mode) for c in vocab], dtype=np.float32
        )
        scores += KEY_BONUS * in_key[np.newaxis, :]

    # "No chord" wins wherever the beat carries almost no harmonic energy.
    reference = float(np.median(energy)) if energy.size else 0.0
    quiet = energy < reference * SILENCE_RATIO
    scores[quiet, :] -= 6.0
    scores[quiet, 0] += 12.0

    return scores, vocab


def viterbi(scores: np.ndarray, self_bonus: float = SELF_TRANSITION_BONUS) -> np.ndarray:
    """Decode the most likely chord path through ``scores`` (``(n_beats, n_chords)``).

    The transition model is deliberately simple: any chord may follow any other,
    but staying put costs nothing extra while switching pays ``self_bonus``. That
    single knob controls how eager the output is to change chord.
    """
    n_frames, n_states = scores.shape
    if n_frames == 0:
        return np.zeros(0, dtype=int)

    best = scores[0].astype(np.float64).copy()
    backpointers = np.zeros((n_frames, n_states), dtype=np.int32)

    for t in range(1, n_frames):
        # Switching to any state costs the same, so the best predecessor for a
        # switch is simply the global best -- no need for an O(n^2) scan.
        best_prev = int(np.argmax(best))
        switch_value = best[best_prev]
        stay_value = best + self_bonus

        take_stay = stay_value > switch_value
        backpointers[t] = np.where(take_stay, np.arange(n_states), best_prev)
        best = np.where(take_stay, stay_value, switch_value) + scores[t]

    path = np.zeros(n_frames, dtype=int)
    path[-1] = int(np.argmax(best))
    for t in range(n_frames - 1, 0, -1):
        path[t - 1] = backpointers[t, path[t]]
    return path


def estimate_key(chroma: np.ndarray) -> tuple[int, str, float]:
    """Krumhansl-Schmuckler key estimation over an averaged chroma vector.

    Returns ``(tonic, mode, confidence)`` where confidence is the margin between
    the winning correlation and the runner-up, normalised to ``0..1``.
    """
    if chroma.size == 0:
        return 0, "major", 0.0

    averaged = chroma.mean(axis=1).astype(np.float64)
    if averaged.sum() <= 0:
        return 0, "major", 0.0
    averaged = averaged / averaged.sum()

    results: list[tuple[float, int, str]] = []
    for mode, profile in (("major", theory.MAJOR_PROFILE), ("minor", theory.MINOR_PROFILE)):
        reference = np.asarray(profile, dtype=np.float64)
        reference = (reference - reference.mean()) / np.linalg.norm(reference - reference.mean())
        for tonic in range(12):
            rotated = np.roll(averaged, -tonic)
            centered = rotated - rotated.mean()
            norm = np.linalg.norm(centered)
            correlation = 0.0 if norm == 0 else float(centered @ reference / norm)
            results.append((correlation, tonic, mode))

    results.sort(reverse=True)
    best, runner_up = results[0], results[1]
    confidence = float(np.clip((best[0] - runner_up[0]) * 4.0, 0.0, 1.0))
    return best[1], best[2], confidence


def decode(
    chroma: np.ndarray,
    bass_chroma: np.ndarray | None = None,
    self_bonus: float = SELF_TRANSITION_BONUS,
) -> tuple[list[Chord], np.ndarray, tuple[int, str, float]]:
    """Full chord decoding for a beat-synchronous chroma matrix.

    Key estimation runs first and then feeds back into the emission scores, so
    diatonic chords get the benefit of the doubt on ambiguous beats.
    """
    tonic, mode, key_confidence = estimate_key(chroma)
    scores, vocab = emission_scores(chroma, bass_chroma, key=(tonic, mode))
    path = viterbi(scores, self_bonus=self_bonus)

    # Per-beat confidence: softmax probability of the decoded chord.
    shifted = scores - scores.max(axis=1, keepdims=True)
    probabilities = np.exp(shifted)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    confidences = probabilities[np.arange(len(path)), path]

    return [vocab[i] for i in path], confidences, (tonic, mode, key_confidence)
