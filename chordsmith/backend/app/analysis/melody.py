"""Lead-line transcription: pitch tracking, note segmentation, solo detection.

This is the part Chordify does not do. Chords tell you what to strum; a
transcribed lead line tells you what to play when the guitar takes over. The
pipeline is:

    audio -> probabilistic pitch track (pYIN) -> note segmentation
          -> per-bar activity stats -> lead sections, some flagged as solos

Everything here works on the *dominant* pitch at each instant. It is honest
monophonic transcription: on a clean lead it is accurate, on a dense mix it
follows whichever voice is loudest, and it makes no attempt at source
separation.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import scipy.signal as signal
import librosa

from .beats import HOP_LENGTH

# Pitch search range. pYIN locks onto the strongest fundamental it can find, and
# in a full mix that is usually the bass, not the lead. Starting at C3 puts the
# bass register out of reach; the top end covers a 24-fret guitar.
FMIN = librosa.note_to_hz("C3")
FMAX = librosa.note_to_hz("E6")

# Bass energy still leaks in through harmonics, so it is filtered out before
# tracking. 185 Hz sits below the search range but above most bass fundamentals.
HIGHPASS_HZ = 185.0

# A note has to hold for this long to count; shorter runs are pitch-tracker
# jitter rather than something a player would articulate.
MIN_NOTE_SECONDS = 0.07

# Frames below this voicing probability are treated as "no lead sounding".
VOICED_THRESHOLD = 0.55

# A bar counts as carrying a lead line when this much of it is voiced and it
# holds at least this many notes. The ratio is low on purpose: a staccato phrase
# leaves most of the bar silent between notes yet is unmistakably a lead line,
# so the note count is what carries the decision.
LEAD_VOICED_RATIO = 0.22
LEAD_MIN_NOTES_PER_BAR = 2

# A lead section is called a solo when it moves this fast (notes per bar) and
# ranges at least this wide. Held vocal lines fail both tests; instrumental
# solos pass them comfortably.
SOLO_NOTES_PER_BAR = 3.0
SOLO_RANGE_SEMITONES = 5


@dataclass
class Note:
    start: float
    end: float
    midi: int
    confidence: float
    velocity: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class LeadSection:
    start_bar: int
    end_bar: int
    start: float
    end: float
    note_count: int
    notes_per_bar: float
    low_midi: int
    high_midi: int
    is_solo: bool


def suppress_bass(y: np.ndarray, sr: int) -> np.ndarray:
    """High-pass the signal so pitch tracking follows the lead, not the bass."""
    if sr <= 2 * HIGHPASS_HZ:
        return y
    sos = signal.butter(4, HIGHPASS_HZ / (sr / 2), btype="highpass", output="sos")
    return signal.sosfiltfilt(sos, y).astype(np.float32)


def track_pitch(y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Run pYIN and return ``(midi, voiced_probability, times)``.

    ``midi`` is NaN wherever no pitch was found. pYIN is used rather than a bare
    autocorrelation because its Viterbi decoding over pitch candidates is what
    keeps octave errors down on real recordings.
    """
    f0, _, voiced_probability = librosa.pyin(
        suppress_bass(y, sr),
        fmin=float(FMIN),
        fmax=float(FMAX),
        sr=sr,
        frame_length=2048,
        hop_length=HOP_LENGTH,
        fill_na=np.nan,
    )
    times = librosa.times_like(f0, sr=sr, hop_length=HOP_LENGTH)
    with np.errstate(divide="ignore", invalid="ignore"):
        midi = librosa.hz_to_midi(f0)
    return midi, np.nan_to_num(voiced_probability), times


def _smooth(midi: np.ndarray, width: int = 5) -> np.ndarray:
    """Median-filter the pitch track, ignoring unvoiced frames."""
    if len(midi) < width:
        return midi
    padded = np.pad(midi, width // 2, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, width)
    # Windows sitting entirely in an unvoiced stretch are all-NaN; the median of
    # nothing is NaN, which is the right answer, so the warning is just noise.
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        smoothed = np.nanmedian(windows, axis=1)
    # Never invent pitch where none was detected.
    smoothed[np.isnan(midi)] = np.nan
    return smoothed


def detect_onsets(y: np.ndarray, sr: int, times: np.ndarray) -> np.ndarray:
    """Frame indices where a new note is articulated.

    Pitch alone cannot separate two of the same note played in a row — the
    tracker sees one continuous pitch. Onsets supply the missing boundary, which
    is what stops a repeated note from collapsing into a single long one.
    """
    envelope = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP_LENGTH)
    frames = librosa.onset.onset_detect(
        onset_envelope=envelope, sr=sr, hop_length=HOP_LENGTH, backtrack=True, units="frames"
    )
    return np.asarray(frames)[np.asarray(frames) < len(times)] if len(frames) else np.zeros(0, int)


def _correct_octaves(notes: list[Note], window: int = 4) -> None:
    """Pull isolated octave jumps back in line with their neighbours.

    pYIN occasionally locks onto a harmonic for a single note, which shows up as
    one note sitting an octave off a line that is otherwise stepwise. Only such
    outliers are moved, and only when the shift genuinely brings them into the
    surrounding range.
    """
    if len(notes) < 3:
        return
    pitches = [note.midi for note in notes]
    for index, note in enumerate(notes):
        low = max(index - window, 0)
        high = min(index + window + 1, len(notes))
        neighbours = [pitches[i] for i in range(low, high) if i != index]
        if not neighbours:
            continue
        reference = float(np.median(neighbours))
        distance = note.midi - reference
        if abs(distance) < 11:
            continue
        shift = -12 if distance > 0 else 12
        if abs(note.midi + shift - reference) <= 7:
            notes[index] = Note(
                start=note.start,
                end=note.end,
                midi=note.midi + shift,
                confidence=note.confidence * 0.9,  # a corrected note is less certain
                velocity=note.velocity,
            )


def segment_notes(
    midi: np.ndarray,
    voiced_probability: np.ndarray,
    times: np.ndarray,
    rms: np.ndarray,
    onset_frames: np.ndarray | None = None,
) -> list[Note]:
    """Turn a frame-wise pitch track into discrete notes."""
    smoothed = _smooth(midi, width=3)
    voiced = (voiced_probability >= VOICED_THRESHOLD) & ~np.isnan(smoothed)
    if not voiced.any():
        return []

    quantized = np.where(voiced, np.round(smoothed), np.nan)
    frame_duration = float(times[1] - times[0]) if len(times) > 1 else 0.02
    min_frames = max(int(round(MIN_NOTE_SECONDS / frame_duration)), 2)
    onsets = set(int(frame) for frame in (onset_frames if onset_frames is not None else []))

    notes: list[Note] = []
    start_index: int | None = None

    def flush(end_index: int) -> None:
        if start_index is None or end_index - start_index < min_frames:
            return
        window = slice(start_index, end_index)
        segment = quantized[window]
        if np.all(np.isnan(segment)):
            return
        notes.append(
            Note(
                start=float(times[start_index]),
                end=float(times[min(end_index, len(times) - 1)]),
                midi=int(np.round(np.nanmedian(segment))),
                confidence=float(np.mean(voiced_probability[window])),
                velocity=float(np.mean(rms[window])) if rms.size else 0.0,
            )
        )

    current_pitch: float | None = None
    for index in range(len(quantized)):
        pitch = quantized[index]
        if np.isnan(pitch):
            flush(index)
            start_index, current_pitch = None, None
            continue
        # A new note starts on a pitch change, after silence, or on an onset.
        if current_pitch is None or pitch != current_pitch or index in onsets:
            flush(index)
            start_index, current_pitch = index, pitch
    flush(len(quantized))

    _correct_octaves(notes)
    return notes


def find_lead_sections(
    notes: list[Note],
    voiced_probability: np.ndarray,
    times: np.ndarray,
    bar_bounds: list[tuple[int, float, float]],
) -> list[LeadSection]:
    """Group bars carrying a lead line into sections, flagging likely solos.

    ``bar_bounds`` is ``(bar_number, start_time, end_time)`` per bar.
    """
    if not bar_bounds:
        return []

    voiced = voiced_probability >= VOICED_THRESHOLD
    active_bars: list[tuple[int, float, float, list[Note]]] = []

    for number, start, end in bar_bounds:
        frame_mask = (times >= start) & (times < end)
        if not frame_mask.any():
            continue
        ratio = float(voiced[frame_mask].mean())
        bar_notes = [note for note in notes if note.start < end and note.end > start]
        if ratio >= LEAD_VOICED_RATIO and len(bar_notes) >= LEAD_MIN_NOTES_PER_BAR:
            active_bars.append((number, start, end, bar_notes))

    sections: list[LeadSection] = []
    run: list[tuple[int, float, float, list[Note]]] = []

    def close_run() -> None:
        if not run:
            return
        bars = len(run)
        collected = {id(note): note for _, _, _, bar_notes in run for note in bar_notes}
        run_notes = list(collected.values())
        pitches = [note.midi for note in run_notes]
        notes_per_bar = len(run_notes) / bars
        pitch_range = max(pitches) - min(pitches)
        sections.append(
            LeadSection(
                start_bar=run[0][0],
                end_bar=run[-1][0],
                start=run[0][1],
                end=run[-1][2],
                note_count=len(run_notes),
                notes_per_bar=notes_per_bar,
                low_midi=min(pitches),
                high_midi=max(pitches),
                is_solo=notes_per_bar >= SOLO_NOTES_PER_BAR
                and pitch_range >= SOLO_RANGE_SEMITONES,
            )
        )
        run.clear()

    for bar in active_bars:
        if run and bar[0] != run[-1][0] + 1:
            close_run()
        run.append(bar)
    close_run()

    return sections


def extract_lead(
    y_harmonic: np.ndarray,
    sr: int,
    bar_bounds: list[tuple[int, float, float]],
) -> tuple[list[Note], list[LeadSection], float]:
    """Full lead extraction. Returns ``(notes, sections, voiced_coverage)``."""
    lead_band = suppress_bass(y_harmonic, sr)
    midi, voiced_probability, times = track_pitch(y_harmonic, sr)
    rms = librosa.feature.rms(y=lead_band, hop_length=HOP_LENGTH)[0]
    if len(rms) < len(times):
        rms = np.pad(rms, (0, len(times) - len(rms)), mode="edge")
    rms = rms[: len(times)]
    peak = rms.max() if rms.size else 0.0
    rms = rms / peak if peak > 0 else rms

    onsets = detect_onsets(lead_band, sr, times)
    notes = segment_notes(midi, voiced_probability, times, rms, onsets)
    sections = find_lead_sections(notes, voiced_probability, times, bar_bounds)
    coverage = float((voiced_probability >= VOICED_THRESHOLD).mean()) if len(times) else 0.0
    return notes, sections, coverage
