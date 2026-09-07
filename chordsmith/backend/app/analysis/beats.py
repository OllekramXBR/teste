"""Beat tracking, meter estimation and downbeat phase detection."""

from __future__ import annotations

import numpy as np
import librosa

DEFAULT_SR = 22050
HOP_LENGTH = 512

# Meters the tracker will consider, in the order it prefers them on a tie.
CANDIDATE_METERS = (4, 3)


def track_beats(
    y_percussive: np.ndarray, sr: int = DEFAULT_SR
) -> tuple[float, np.ndarray, np.ndarray]:
    """Estimate tempo and beat positions from the percussive signal.

    Returns ``(bpm, beat_times, onset_envelope)``. The onset envelope is handed
    back because downbeat detection reuses it.
    """
    onset_envelope = librosa.onset.onset_strength(
        y=y_percussive, sr=sr, hop_length=HOP_LENGTH, aggregate=np.median
    )
    bpm, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_envelope, sr=sr, hop_length=HOP_LENGTH, trim=False, units="frames"
    )
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP_LENGTH)

    tempo = float(np.atleast_1d(bpm)[0])
    if not np.isfinite(tempo) or tempo <= 0:
        tempo = _tempo_from_intervals(beat_times)

    return tempo, np.asarray(beat_times, dtype=float), onset_envelope


def _tempo_from_intervals(beat_times: np.ndarray) -> float:
    if len(beat_times) < 2:
        return 0.0
    median_interval = float(np.median(np.diff(beat_times)))
    return 60.0 / median_interval if median_interval > 0 else 0.0


def onset_strength_at_beats(
    onset_envelope: np.ndarray, beat_times: np.ndarray, sr: int = DEFAULT_SR
) -> np.ndarray:
    """Sample the onset envelope at each beat position."""
    if len(beat_times) == 0:
        return np.zeros(0)
    frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=HOP_LENGTH)
    frames = np.clip(frames, 0, len(onset_envelope) - 1)
    values = onset_envelope[frames]
    peak = values.max()
    return values / peak if peak > 0 else values


def chord_change_score(chord_indices: np.ndarray) -> np.ndarray:
    """1.0 on beats where the chord differs from the previous beat, else 0.0."""
    if len(chord_indices) == 0:
        return np.zeros(0)
    changes = np.zeros(len(chord_indices))
    changes[0] = 1.0
    changes[1:] = (np.diff(chord_indices) != 0).astype(float)
    return changes


def estimate_downbeats(
    beat_times: np.ndarray,
    onset_envelope: np.ndarray,
    chord_indices: np.ndarray,
    sr: int = DEFAULT_SR,
) -> tuple[int, int]:
    """Pick the meter and the downbeat phase.

    Two cues are combined: percussive accent (downbeats are usually the loudest
    beat of the bar) and harmonic rhythm (chord changes overwhelmingly land on
    downbeats). For each candidate meter and each possible phase, the beats that
    would be downbeats are scored; the highest-scoring combination wins.

    Returns ``(beats_per_bar, phase)`` where ``phase`` is the index of the first
    downbeat.
    """
    n_beats = len(beat_times)
    if n_beats == 0:
        return 4, 0

    accents = onset_strength_at_beats(onset_envelope, beat_times, sr=sr)
    changes = chord_change_score(chord_indices)
    combined = 0.45 * accents + 0.55 * changes

    best_score = -np.inf
    best: tuple[int, int] = (4, 0)

    for meter in CANDIDATE_METERS:
        if n_beats < meter * 2:
            continue
        for phase in range(meter):
            downbeat_positions = np.arange(phase, n_beats, meter)
            other = np.setdiff1d(np.arange(n_beats), downbeat_positions, assume_unique=False)
            if len(downbeat_positions) == 0 or len(other) == 0:
                continue
            # Contrast, not raw mean: a phase is only right if the beats it
            # selects stand out from the ones it does not.
            score = combined[downbeat_positions].mean() - combined[other].mean()
            if meter == 4:
                score += 0.05  # 4/4 is the safe default when the cues are level
            if score > best_score:
                best_score, best = score, (meter, phase)

    return best
