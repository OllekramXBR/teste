"""Source separation: split a mix into vocals, drums, bass and everything else.

This is the piece the rest of the analysis kept apologising for. With the stems
in hand:

* the lyric transcriber hears a voice instead of a band, which is the single
  biggest quality lever available to it;
* the chord decoder can be handed a mix with the singing removed, so a held
  vocal note stops colouring the chroma;
* the lead transcriber can follow the *instrument* rather than whichever voice
  happens to be highest, which was the known failure of solo detection;
* and the player can mute one stem so a guitarist can play that part live.

Demucs (htdemucs) does the separation. It is a PyTorch model and there is no
usable GPU on the target box, so everything here is arranged around CPU cost:
the audio is fed in as a tensor the project already decoded, inference is
segmented so peak memory stays bounded, and the result is written as Ogg
Vorbis — one file per stem, small enough to stream four of them at once.

Four stems, not sixteen. Splitting drums into kick/snare/hats or separating
rhythm from lead guitar needs a different model than this one, and pretending
otherwise would just produce four labels over the same audio.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import STEM_FORMAT, STEM_MODEL, STEM_SEGMENT, STEM_SR, STEMS_DIR

logger = logging.getLogger(__name__)

# The order the mixer shows them in: what you are most likely to want to silence
# first comes first.
STEM_NAMES = ("vocals", "drums", "bass", "other")

# Portuguese labels for the UI; the file names stay in English so the model's
# own naming and ours never diverge.
STEM_LABELS_PT = {
    "vocals": "Voz",
    "drums": "Bateria",
    "bass": "Baixo",
    "other": "Outros",
}

_separator = None


@dataclass
class StemFile:
    name: str
    path: Path
    bytes: int


def get_separator():
    """Build the Demucs separator once per process.

    Weights download on first use into the model directory under the data
    volume, so a rebuilt container does not fetch them again.
    """
    global _separator
    if _separator is None:
        from demucs.api import Separator

        logger.info("loading separation model %s", STEM_MODEL)
        _separator = Separator(
            model=STEM_MODEL,
            device="cpu",
            # Inference over the whole track at once is what makes Demucs
            # memory-hungry. Cutting it into segments trades a little speed for
            # a peak that fits alongside everything else on the box.
            segment=STEM_SEGMENT,
            progress=False,
        )
    return _separator


def load_stereo(path: str | Path, sr: int = STEM_SR) -> np.ndarray:
    """Load audio as ``(2, n)`` at the model's rate.

    Demucs is trained on 44.1 kHz stereo. A mono file is duplicated rather than
    left one-channel, because the model's first convolution expects two.
    """
    import librosa

    audio, _ = librosa.load(str(path), sr=sr, mono=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = np.stack([audio, audio])
    return audio


def separate(path: str | Path, song_id: str) -> list[StemFile]:
    """Separate one file and write the stems, returning what was written."""
    import soundfile as sf
    import torch

    audio = load_stereo(path)
    separator = get_separator()

    tensor = torch.from_numpy(audio)
    _, sources = separator.separate_tensor(tensor, STEM_SR)

    destination = STEMS_DIR / song_id
    destination.mkdir(parents=True, exist_ok=True)

    written: list[StemFile] = []
    for name in STEM_NAMES:
        if name not in sources:
            continue
        samples = sources[name].detach().cpu().numpy().T  # soundfile wants (n, channels)
        target = destination / f"{name}.{STEM_FORMAT}"
        sf.write(str(target), samples, STEM_SR, format=STEM_FORMAT.upper())
        written.append(StemFile(name=name, path=target, bytes=target.stat().st_size))
        logger.info("wrote stem %s for %s (%d bytes)", name, song_id, written[-1].bytes)

    return written


def stem_path(song_id: str, name: str) -> Path | None:
    """Path of one stored stem, or ``None`` when it was never produced."""
    if name not in STEM_NAMES:
        return None
    candidate = STEMS_DIR / song_id / f"{name}.{STEM_FORMAT}"
    return candidate if candidate.exists() else None


def available_stems(song_id: str) -> list[str]:
    return [name for name in STEM_NAMES if stem_path(song_id, name) is not None]


def delete_stems(song_id: str) -> None:
    directory = STEMS_DIR / song_id
    if not directory.exists():
        return
    for entry in directory.iterdir():
        entry.unlink(missing_ok=True)
    directory.rmdir()


def load_stem_mono(song_id: str, names: list[str], sr: int) -> np.ndarray | None:
    """Sum one or more stems back to mono at ``sr``, for feeding an analyser.

    Returns ``None`` when none of the requested stems exist, so every caller can
    fall back to the original mix without special-casing.
    """
    import librosa

    paths = [stem_path(song_id, name) for name in names]
    present = [path for path in paths if path is not None]
    if not present:
        return None

    mixed: np.ndarray | None = None
    for path in present:
        audio, _ = librosa.load(str(path), sr=sr, mono=True)
        mixed = audio if mixed is None else mixed[: len(audio)] + audio[: len(mixed)]
    return mixed
