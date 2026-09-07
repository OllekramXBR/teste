"""Stems re-rendered in another key, or at another tempo.

Transposing recorded audio means either shifting pitch without changing speed or
changing speed without shifting pitch, and both are the same expensive operation
— a phase vocoder walking the whole file.

That work is done here, on the server, ahead of time, and written to disk. It
could instead be done in the browser during playback, and that is how most
players do it. It is the wrong choice for this one: the device is a tablet on
stage, the alternative to a glitch is nothing, and a phase vocoder running live
across five simultaneous stems is exactly the kind of load that produces one.
Rendering ahead means the stage view keeps doing the only thing it has to do
reliably, which is play files.

Each combination is cached under its own directory, so asking for the same key
twice costs nothing the second time.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..config import STEM_FORMAT, STEMS_DIR
from . import stems as stem_module

logger = logging.getLogger(__name__)

# Rendering is per semitone and per speed, so the space of variants is large and
# mostly useless. A singer moves a song by a few semitones, not eleven, and
# practice speeds live between half and full.
MAX_SEMITONES = 7
MIN_RATE = 0.5
MAX_RATE = 1.5

# The sample rate variants are rendered at. Lower than the stems themselves,
# because a phase vocoder's cost scales with it and this is a monitor mix, not
# a master.
VARIANT_SR = 44100


def variant_key(semitones: int, rate: float) -> str:
    """Directory name for one combination; ``t0_r100`` is the original."""
    return f"t{semitones:+d}_r{int(round(rate * 100))}".replace("+", "p").replace("-", "m")


def variant_dir(song_id: str, semitones: int, rate: float) -> Path:
    return STEMS_DIR / song_id / "variants" / variant_key(semitones, rate)


def available(song_id: str) -> list[dict]:
    """Every rendered variant of this song, newest first."""
    root = STEMS_DIR / song_id / "variants"
    if not root.is_dir():
        return []
    found: list[dict] = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        names = sorted(path.stem for path in directory.glob(f"*.{STEM_FORMAT}"))
        if names:
            found.append({"key": directory.name, "stems": names})
    return found


def render(song_id: str, semitones: int, rate: float) -> list[str]:
    """Write one transposed and/or time-stretched copy of every stem.

    Returns the stem names written. Refuses combinations outside the useful
    range rather than spending twenty minutes producing something nobody asked
    for by accident.
    """
    import librosa
    import soundfile as sf

    if abs(semitones) > MAX_SEMITONES:
        raise ValueError(f"Transposição fora do alcance útil (±{MAX_SEMITONES} semitons)")
    if not MIN_RATE <= rate <= MAX_RATE:
        raise ValueError(f"Andamento fora do alcance útil ({MIN_RATE}–{MAX_RATE}×)")
    if semitones == 0 and abs(rate - 1.0) < 1e-6:
        raise ValueError("Essa é a gravação original — não há o que renderizar")

    destination = variant_dir(song_id, semitones, rate)
    destination.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for name in stem_module.STEM_NAMES:
        source = stem_module.stem_path(song_id, name)
        if source is None:
            continue

        audio, _ = librosa.load(str(source), sr=VARIANT_SR, mono=True)
        if audio.size == 0:
            continue

        # Order matters and this one is deliberate: stretching first and then
        # shifting would shift a signal whose transients have already been
        # smeared, and the artefacts compound. Pitch first keeps the smearing
        # to one pass.
        if semitones:
            audio = librosa.effects.pitch_shift(y=audio, sr=VARIANT_SR, n_steps=semitones)
        if abs(rate - 1.0) > 1e-6:
            audio = librosa.effects.time_stretch(y=audio, rate=rate)

        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak > 1.0:
            # A phase vocoder can add a few percent of headroom back; clipping
            # five stems on top of each other is audible where one is not.
            audio = audio / peak

        target = destination / f"{name}.{STEM_FORMAT}"
        sf.write(str(target), audio, VARIANT_SR, format=STEM_FORMAT.upper())
        written.append(name)
        logger.info("rendered %s of %s at %+d semitones, %.2fx", name, song_id, semitones, rate)

    return written
