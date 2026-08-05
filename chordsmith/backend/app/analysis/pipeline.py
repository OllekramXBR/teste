"""End-to-end analysis: an audio file in, a beat-aligned chord chart out."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import librosa

from . import beats as beat_module
from . import chords as chord_module
from . import melody as melody_module
from . import tab as tab_module
from . import theory
from .beats import DEFAULT_SR, HOP_LENGTH
from .melody import LeadSection, Note
from .theory import Chord

# Chroma is computed over this pitch range. Starting at C1 keeps the bass in
# range; six octaves reach well past where chord tones carry information.
CQT_FMIN = librosa.note_to_hz("C1")
CQT_OCTAVES = 6
BINS_PER_OCTAVE = 36

# The bass chroma looks only at the bottom two octaves, where the root lives.
BASS_FMIN = librosa.note_to_hz("C1")
BASS_FMAX = librosa.note_to_hz("C3")


@dataclass
class BeatEvent:
    index: int
    time: float
    duration: float
    bar: int
    beat_in_bar: int
    downbeat: bool
    chord: Chord
    confidence: float


@dataclass
class ChordSpan:
    """A run of consecutive beats sharing one chord."""

    chord: Chord
    start: float
    end: float
    start_beat: int
    end_beat: int
    confidence: float


@dataclass
class TabNote:
    """A transcribed lead note placed on the fretboard and on the beat grid."""

    note: Note
    string: int | None
    fret: int | None
    beat: int
    bar: int


@dataclass
class AnalysisResult:
    duration: float
    bpm: float
    beats_per_bar: int
    key_tonic: int
    key_mode: str
    key_confidence: float
    beat_events: list[BeatEvent] = field(default_factory=list)
    spans: list[ChordSpan] = field(default_factory=list)
    tab_notes: list[TabNote] = field(default_factory=list)
    lead_sections: list[LeadSection] = field(default_factory=list)
    lead_coverage: float = 0.0
    analysis_seconds: float = 0.0

    @property
    def uses_flats(self) -> bool:
        return theory.key_uses_flats(self.key_tonic, self.key_mode)

    def to_dict(self) -> dict:
        flats = self.uses_flats
        return {
            "duration": round(self.duration, 3),
            "bpm": round(self.bpm, 2),
            "beatsPerBar": self.beats_per_bar,
            "key": {
                "tonic": self.key_tonic,
                "mode": self.key_mode,
                "name": theory.key_name(self.key_tonic, self.key_mode),
                "confidence": round(self.key_confidence, 3),
            },
            "useFlats": flats,
            "beats": [
                {
                    "index": b.index,
                    "time": round(b.time, 4),
                    "duration": round(b.duration, 4),
                    "bar": b.bar,
                    "beatInBar": b.beat_in_bar,
                    "downbeat": b.downbeat,
                    "root": b.chord.root,
                    "quality": b.chord.quality,
                    "label": b.chord.label(flats),
                    "notes": list(b.chord.pitch_classes()),
                    "confidence": round(float(b.confidence), 3),
                }
                for b in self.beat_events
            ],
            "chords": [
                {
                    "label": s.chord.label(flats),
                    "root": s.chord.root,
                    "quality": s.chord.quality,
                    "notes": list(s.chord.pitch_classes()),
                    "start": round(s.start, 4),
                    "end": round(s.end, 4),
                    "startBeat": s.start_beat,
                    "endBeat": s.end_beat,
                    "confidence": round(float(s.confidence), 3),
                }
                for s in self.spans
            ],
            "uniqueChords": sorted(
                {s.chord.label(flats) for s in self.spans if not s.chord.is_none}
            ),
            "lead": {
                "tuning": list(tab_module.GUITAR_TUNING),
                "stringNames": list(tab_module.GUITAR_STRING_NAMES),
                "coverage": round(self.lead_coverage, 3),
                "notes": [
                    {
                        "start": round(t.note.start, 4),
                        "end": round(t.note.end, 4),
                        "midi": t.note.midi,
                        "name": tab_module.note_name(t.note.midi),
                        "string": t.string,
                        "fret": t.fret,
                        "beat": t.beat,
                        "bar": t.bar,
                        "confidence": round(t.note.confidence, 3),
                        "velocity": round(t.note.velocity, 3),
                    }
                    for t in self.tab_notes
                ],
                "sections": [
                    {
                        "startBar": s.start_bar,
                        "endBar": s.end_bar,
                        "start": round(s.start, 3),
                        "end": round(s.end, 3),
                        "noteCount": s.note_count,
                        "notesPerBar": round(s.notes_per_bar, 2),
                        "lowMidi": s.low_midi,
                        "highMidi": s.high_midi,
                        "lowName": tab_module.note_name(s.low_midi),
                        "highName": tab_module.note_name(s.high_midi),
                        "isSolo": s.is_solo,
                    }
                    for s in self.lead_sections
                ],
            },
            "analysisSeconds": round(self.analysis_seconds, 2),
        }


def load_audio(path: str | Path, sr: int = DEFAULT_SR) -> tuple[np.ndarray, int]:
    """Load an audio file as mono at ``sr``."""
    y, loaded_sr = librosa.load(str(path), sr=sr, mono=True)
    return y, loaded_sr


def beat_synchronous_chroma(
    y_harmonic: np.ndarray, beat_times: np.ndarray, sr: int
) -> tuple[np.ndarray, np.ndarray]:
    """Aggregate chroma over each beat.

    Returns full-range and bass-only chroma matrices, both ``(12, n_beats)``.
    The median over each beat is used rather than the mean so a single
    percussive frame cannot colour the whole beat.
    """
    chroma = librosa.feature.chroma_cqt(
        y=y_harmonic,
        sr=sr,
        hop_length=HOP_LENGTH,
        fmin=CQT_FMIN,
        n_octaves=CQT_OCTAVES,
        bins_per_octave=BINS_PER_OCTAVE,
    )
    # Soft compression keeps loud sections from dominating the templates.
    chroma = np.minimum(chroma, librosa.util.normalize(chroma, norm=np.inf, axis=0))

    bass_cqt = np.abs(
        librosa.cqt(
            y=y_harmonic,
            sr=sr,
            hop_length=HOP_LENGTH,
            fmin=BASS_FMIN,
            n_bins=int(round(12 * np.log2(BASS_FMAX / BASS_FMIN))),
            bins_per_octave=12,
        )
    )
    bass_chroma = librosa.feature.chroma_cqt(
        C=bass_cqt, sr=sr, hop_length=HOP_LENGTH, fmin=BASS_FMIN, bins_per_octave=12
    )

    if len(beat_times) == 0:
        return chroma, bass_chroma

    beat_frames = librosa.time_to_frames(beat_times, sr=sr, hop_length=HOP_LENGTH)
    beat_frames = np.clip(beat_frames, 0, chroma.shape[1] - 1)
    sync = librosa.util.sync(chroma, beat_frames, aggregate=np.median, pad=False)
    bass_sync = librosa.util.sync(bass_chroma, beat_frames, aggregate=np.median, pad=False)

    # librosa.util.sync with pad=False yields one column per interval between
    # boundaries, i.e. one fewer than the number of beats. The last beat gets
    # the frames from its onset to the end of the track.
    if sync.shape[1] == len(beat_times) - 1:
        tail = chroma[:, beat_frames[-1] :]
        tail_bass = bass_chroma[:, beat_frames[-1] :]
        last = np.median(tail, axis=1, keepdims=True) if tail.size else np.zeros((12, 1))
        last_bass = (
            np.median(tail_bass, axis=1, keepdims=True) if tail_bass.size else np.zeros((12, 1))
        )
        sync = np.hstack([sync, last])
        bass_sync = np.hstack([bass_sync, last_bass])

    return sync, bass_sync


def build_spans(events: list[BeatEvent]) -> list[ChordSpan]:
    """Collapse consecutive beats carrying the same chord into spans."""
    spans: list[ChordSpan] = []
    for event in events:
        if spans and spans[-1].chord == event.chord:
            current = spans[-1]
            current.end = event.time + event.duration
            current.end_beat = event.index
            current.confidence = max(current.confidence, event.confidence)
        else:
            spans.append(
                ChordSpan(
                    chord=event.chord,
                    start=event.time,
                    end=event.time + event.duration,
                    start_beat=event.index,
                    end_beat=event.index,
                    confidence=event.confidence,
                )
            )
    return spans


def analyze_file(path: str | Path, sr: int = DEFAULT_SR) -> AnalysisResult:
    """Run the whole pipeline on one audio file."""
    started = time.perf_counter()
    y, sr = load_audio(path, sr=sr)
    duration = float(len(y) / sr) if sr else 0.0

    if len(y) < sr:  # under a second of audio: nothing to analyse
        return AnalysisResult(
            duration=duration,
            bpm=0.0,
            beats_per_bar=4,
            key_tonic=0,
            key_mode="major",
            key_confidence=0.0,
            analysis_seconds=time.perf_counter() - started,
        )

    y_harmonic, y_percussive = librosa.effects.hpss(y)

    bpm, beat_times, onset_envelope = beat_module.track_beats(y_percussive, sr=sr)
    if len(beat_times) == 0:
        beat_times = np.arange(0.0, duration, 0.5)

    chroma, bass_chroma = beat_synchronous_chroma(y_harmonic, beat_times, sr)
    n_beats = min(len(beat_times), chroma.shape[1])
    beat_times, chroma, bass_chroma = (
        beat_times[:n_beats],
        chroma[:, :n_beats],
        bass_chroma[:, :n_beats],
    )

    chord_sequence, confidences, (tonic, mode, key_confidence) = chord_module.decode(
        chroma, bass_chroma
    )

    chord_ids = np.array(
        [-1 if c.root is None else c.root * 100 + theory.QUALITY_NAMES.index(c.quality) for c in chord_sequence]
    )
    beats_per_bar, phase = beat_module.estimate_downbeats(
        beat_times, onset_envelope, chord_ids, sr=sr
    )

    events: list[BeatEvent] = []
    for index, (start, chord) in enumerate(zip(beat_times, chord_sequence)):
        end = beat_times[index + 1] if index + 1 < len(beat_times) else duration
        position = (index - phase) % beats_per_bar
        events.append(
            BeatEvent(
                index=index,
                time=float(start),
                duration=max(float(end - start), 0.0),
                bar=int((index - phase) // beats_per_bar) + 1,
                beat_in_bar=int(position) + 1,
                downbeat=position == 0,
                chord=chord,
                confidence=float(confidences[index]),
            )
        )

    tab_notes, lead_sections, lead_coverage = transcribe_lead(y_harmonic, sr, events)

    return AnalysisResult(
        duration=duration,
        bpm=bpm,
        beats_per_bar=beats_per_bar,
        key_tonic=tonic,
        key_mode=mode,
        key_confidence=key_confidence,
        beat_events=events,
        spans=build_spans(events),
        tab_notes=tab_notes,
        lead_sections=lead_sections,
        lead_coverage=lead_coverage,
        analysis_seconds=time.perf_counter() - started,
    )


def bar_bounds(events: list[BeatEvent]) -> list[tuple[int, float, float]]:
    """Start and end time of each bar, derived from the beat grid."""
    bounds: dict[int, tuple[float, float]] = {}
    for event in events:
        start, end = bounds.get(event.bar, (event.time, event.time))
        bounds[event.bar] = (min(start, event.time), max(end, event.time + event.duration))
    return [(bar, start, end) for bar, (start, end) in sorted(bounds.items())]


def transcribe_lead(
    y_harmonic: np.ndarray, sr: int, events: list[BeatEvent]
) -> tuple[list[TabNote], list[LeadSection], float]:
    """Transcribe the lead line and lay it out as tablature on the beat grid."""
    notes, sections, coverage = melody_module.extract_lead(y_harmonic, sr, bar_bounds(events))
    if not notes:
        return [], sections, coverage

    positions = tab_module.assign_positions([note.midi for note in notes])
    beat_times = np.array([event.time for event in events]) if events else np.zeros(0)

    tab_notes: list[TabNote] = []
    for note, position in zip(notes, positions):
        if beat_times.size:
            beat_index = int(np.searchsorted(beat_times, note.start, side="right") - 1)
            beat_index = max(beat_index, 0)
            bar = events[beat_index].bar
        else:
            beat_index, bar = 0, 1
        tab_notes.append(
            TabNote(
                note=note,
                string=position.string if position else None,
                fret=position.fret if position else None,
                beat=beat_index,
                bar=bar,
            )
        )
    return tab_notes, sections, coverage
