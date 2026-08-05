"""Music theory primitives shared by the analysis engine and the API layer.

Pitch classes are integers in ``0..11`` with ``C = 0``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# Keys whose signature is conventionally written with flats.
FLAT_MAJOR_TONICS = {5, 10, 3, 8, 1, 6}  # F, Bb, Eb, Ab, Db, Gb
FLAT_MINOR_TONICS = {2, 7, 0, 5, 10, 3}  # D, G, C, F, Bb, Eb minor

# Chord vocabulary. Each entry maps a quality suffix to its intervals in
# semitones above the root. The order roughly follows how often a quality shows
# up in popular music, which is also the order used to break scoring ties.
QUALITIES: dict[str, tuple[int, ...]] = {
    "": (0, 4, 7),  # major
    "m": (0, 3, 7),  # minor
    "7": (0, 4, 7, 10),  # dominant seventh
    "m7": (0, 3, 7, 10),
    "maj7": (0, 4, 7, 11),
    "sus4": (0, 5, 7),
    "sus2": (0, 2, 7),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "dim": (0, 3, 6),
    "aug": (0, 4, 8),
    "m7b5": (0, 3, 6, 10),
    "dim7": (0, 3, 6, 9),
}

QUALITY_NAMES = list(QUALITIES)

# Weight given to each chord tone when a template is built. Roots and fifths
# carry the harmonic identity, extensions are comparatively weak in a chroma
# vector, so they get a smaller weight to avoid over-triggering.
INTERVAL_WEIGHTS: dict[int, float] = {
    0: 1.35,  # root
    7: 1.0,  # fifth
    3: 1.0,  # minor third
    4: 1.0,  # major third
    6: 0.9,  # diminished fifth
    8: 0.9,  # augmented fifth
    5: 1.0,  # suspended fourth
    2: 0.9,  # suspended second
    9: 0.65,  # sixth / diminished seventh
    10: 0.7,  # minor seventh
    11: 0.7,  # major seventh
}

# Prior preference per quality, applied as a log-domain bonus during decoding.
# Triads are far more common than four-note chords in the songs this tool is
# aimed at, so without a prior the richer templates win too often.
QUALITY_PRIOR: dict[str, float] = {
    "": 0.55,
    "m": 0.5,
    "7": 0.1,
    "m7": 0.08,
    "maj7": 0.05,
    "sus4": 0.0,
    "sus2": -0.05,
    "6": -0.2,
    "m6": -0.3,
    "dim": -0.25,
    "aug": -0.45,
    "m7b5": -0.4,
    "dim7": -0.45,
}

NO_CHORD_LABEL = "N"


@dataclass(frozen=True)
class Chord:
    """A chord as a root pitch class plus a quality suffix.

    ``root`` is ``None`` for the "no chord" symbol (silence, drums only,
    anything without a clear harmony).
    """

    root: int | None
    quality: str = ""

    @property
    def is_none(self) -> bool:
        return self.root is None

    def pitch_classes(self) -> tuple[int, ...]:
        if self.root is None:
            return ()
        return tuple((self.root + i) % 12 for i in QUALITIES[self.quality])

    def intervals(self) -> tuple[int, ...]:
        if self.root is None:
            return ()
        return QUALITIES[self.quality]

    def label(self, use_flats: bool = False) -> str:
        if self.root is None:
            return NO_CHORD_LABEL
        names = FLAT_NAMES if use_flats else SHARP_NAMES
        return f"{names[self.root]}{self.quality}"

    def transpose(self, semitones: int) -> "Chord":
        if self.root is None:
            return self
        return Chord((self.root + semitones) % 12, self.quality)

    def to_dict(self, use_flats: bool = False) -> dict:
        return {
            "root": self.root,
            "quality": self.quality,
            "label": self.label(use_flats),
            "notes": list(self.pitch_classes()),
        }


NO_CHORD = Chord(None, "")


def chord_vocabulary() -> list[Chord]:
    """Every chord the decoder can emit, "no chord" first."""
    chords: list[Chord] = [NO_CHORD]
    for root in range(12):
        for quality in QUALITY_NAMES:
            chords.append(Chord(root, quality))
    return chords


def note_name(pitch_class: int, use_flats: bool = False) -> str:
    names = FLAT_NAMES if use_flats else SHARP_NAMES
    return names[pitch_class % 12]


def key_uses_flats(tonic: int, mode: str) -> bool:
    """Whether a key is conventionally spelled with flats."""
    if mode == "minor":
        return tonic % 12 in FLAT_MINOR_TONICS
    return tonic % 12 in FLAT_MAJOR_TONICS


def key_name(tonic: int, mode: str) -> str:
    return f"{note_name(tonic, key_uses_flats(tonic, mode))} {mode}"


def transpose_label(label: str, semitones: int, use_flats: bool = False) -> str:
    """Transpose a chord label such as ``"F#m7"`` by ``semitones``."""
    chord = parse_label(label)
    if chord is None:
        return label
    return chord.transpose(semitones).label(use_flats)


def parse_label(label: str) -> Chord | None:
    """Parse a chord label back into a :class:`Chord` (``None`` if unparseable)."""
    label = label.strip()
    if not label or label == NO_CHORD_LABEL:
        return NO_CHORD
    root_len = 2 if len(label) > 1 and label[1] in "#b" else 1
    root_name, quality = label[:root_len], label[root_len:]
    for pitch_class, (sharp, flat) in enumerate(zip(SHARP_NAMES, FLAT_NAMES)):
        if root_name in (sharp, flat):
            if quality not in QUALITIES:
                return None
            return Chord(pitch_class, quality)
    return None


# Krumhansl-Kessler key profiles, the standard correlation templates for
# estimating the tonic and mode of a piece from an averaged chroma vector.
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def diatonic_pitch_classes(tonic: int, mode: str) -> tuple[int, ...]:
    steps = (0, 2, 4, 5, 7, 9, 11) if mode == "major" else (0, 2, 3, 5, 7, 8, 10)
    return tuple((tonic + s) % 12 for s in steps)


def chord_fits_key(chord: Chord, tonic: int, mode: str) -> bool:
    """True when every tone of the chord belongs to the key's scale."""
    if chord.root is None:
        return True
    scale = set(diatonic_pitch_classes(tonic, mode))
    return all(pc in scale for pc in chord.pitch_classes())


def capo_shift(labels: Iterable[str], capo_fret: int, use_flats: bool = False) -> list[str]:
    """Chord shapes to play with a capo on ``capo_fret``.

    A capo raises the sounding pitch, so the shapes fingered behind it are the
    written chords transposed *down* by the fret number. The song still sounds
    in its original key.
    """
    return [transpose_label(label, -capo_fret, use_flats) for label in labels]
