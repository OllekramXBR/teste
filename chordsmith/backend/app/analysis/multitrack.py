"""Transcribing each separated stem into its own line of notes.

Before separation existed, transcription had one hard problem: whatever pitch
tracker you point at a mix follows the loudest voice, and the loudest voice is
usually not the one you wanted. That is why lead detection here has always run
over a high-passed signal — to stop it tracking the bass — and why it still
sometimes followed the singer instead of the guitar.

With the stems that problem is gone. Each part is transcribed from the audio
that contains only that part, in the pitch range that part actually occupies:
the bass line from the bass stem between C1 and C4, the sung line from the lead
vocal stem, and the melody instrument from what is left over. Each one is
monophonic in its own file, which is the case pYIN is good at.

The harmony stem is deliberately not pitch-tracked. It holds chords, and a
monophonic tracker asked to describe a chord will confidently report one note
of it. The chord track already knows the harmony, and it knows it from the
decoder, which was built for that.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from . import melody as melody_module
from . import stems as stem_module
from . import tab as tab_module
from .beats import DEFAULT_SR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Role:
    """A stem, the pitch range it lives in, and what to call it in the file."""

    stem: str
    name: str
    lowest: str
    highest: str
    #: General MIDI program number. Channel 0-indexed elsewhere.
    program: int
    #: Whether to high-pass before tracking, which is only right above the bass.
    suppress_bass: bool


ROLES: tuple[Role, ...] = (
    Role(stem="bass", name="Baixo", lowest="C1", highest="C4", program=33, suppress_bass=False),
    Role(stem="lead", name="Voz principal", lowest="C2", highest="C6", program=52, suppress_bass=True),
    # "other" is what Demucs has left after voice, drums and bass: on most
    # recordings that is the guitars and keys. Transcribing it is the whole
    # reason the tablature can now be about the guitar instead of about
    # whichever voice happened to be highest in the mix.
    Role(stem="other", name="Guitarra e harmonia", lowest="C3", highest="E6", program=26, suppress_bass=True),
)


@dataclass
class TrackNotes:
    name: str
    program: int
    notes: list[melody_module.Note]
    #: Stem this came from, so the interface can say what it is looking at.
    stem: str = ""
    #: Fretboard positions, parallel to ``notes``; empty for parts nobody frets.
    positions: list[tuple[int, int] | None] = field(default_factory=list)


def transcribe_role(audio: np.ndarray, sr: int, role: Role) -> list[melody_module.Note]:
    """Notes for one stem, tracked in that stem's own range."""
    import librosa

    band = melody_module.suppress_bass(audio, sr) if role.suppress_bass else audio

    f0, _, voiced = librosa.pyin(
        band,
        fmin=float(librosa.note_to_hz(role.lowest)),
        fmax=float(librosa.note_to_hz(role.highest)),
        sr=sr,
        frame_length=2048,
        hop_length=melody_module.HOP_LENGTH,
        fill_na=np.nan,
    )
    times = librosa.times_like(f0, sr=sr, hop_length=melody_module.HOP_LENGTH)
    with np.errstate(divide="ignore", invalid="ignore"):
        midi = librosa.hz_to_midi(f0)

    rms = librosa.feature.rms(y=band, hop_length=melody_module.HOP_LENGTH)[0]
    if len(rms) < len(times):
        rms = np.pad(rms, (0, len(times) - len(rms)), mode="edge")
    rms = rms[: len(times)]
    peak = rms.max() if rms.size else 0.0
    if peak > 0:
        rms = rms / peak

    onsets = melody_module.detect_onsets(band, sr, times)
    return melody_module.segment_notes(midi, np.nan_to_num(voiced), times, rms, onsets)


def transcribe_song(song_id: str, sr: int = DEFAULT_SR) -> list[TrackNotes]:
    """Every stem that exists, transcribed into its own track.

    Stems that were never produced are skipped rather than faked, so a song
    separated into fewer parts simply yields fewer tracks.
    """
    tracks: list[TrackNotes] = []
    for role in ROLES:
        audio = stem_module.load_stem_mono(song_id, [role.stem], sr)
        if audio is None or audio.size < sr:
            continue
        notes = transcribe_role(audio, sr, role)
        if not notes:
            logger.info("no notes found in the %s stem of %s", role.stem, song_id)
            continue

        # Fretboard positions for the parts somebody actually frets. The bass
        # and the melody instrument get them; a sung line does not, because a
        # voice has no strings and a tablature of one would be a fiction.
        positions: list[tuple[int, int] | None] = []
        if role.stem in ("other", "bass"):
            placed = tab_module.assign_positions([note.midi for note in notes])
            positions = [
                (position.string, position.fret) if position else None for position in placed
            ]

        tracks.append(
            TrackNotes(
                name=role.name,
                program=role.program,
                notes=notes,
                stem=role.stem,
                positions=positions,
            )
        )
        logger.info("transcribed %d notes from the %s stem of %s", len(notes), role.stem, song_id)
    return tracks
