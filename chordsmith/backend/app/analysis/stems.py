"""Source separation: split a mix into parts that can be muted independently.

This is the piece the rest of the analysis kept apologising for. With the stems
in hand the lyric transcriber hears a voice instead of a band, the chord decoder
can read a mix with the singing removed, the lead transcriber can follow the
instrument rather than whichever voice is highest — and, the reason this exists,
a singer can mute the lead vocal and perform over their own recording.

**Two models, not one.** Demucs splits a mix into vocals, drums, bass and
everything else, and that is where most tools stop. It is not enough here: its
"vocals" holds the lead *and* the backing vocals together, so muting it takes
the harmonies away with the lead and leaves the singer alone over a bare band.
Splitting lead from backing is a different job, done by the karaoke models from
the UVR family, and it runs as a second pass over the vocal stem Demucs
produced.

Everything is rendered ahead of time. Nothing here runs while anyone is on
stage: by then the stems are files, and playing files is something that does not
fail halfway through a chorus.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config import (
    STEM_FORMAT,
    STEM_MODEL_BASE,
    STEM_MODEL_KARAOKE,
    STEM_MODEL_DIR,
    STEMS_DIR,
)

logger = logging.getLogger(__name__)

# The order the mixer shows them in: what you are most likely to silence first
# comes first.
STEM_NAMES = ("lead", "backing", "drums", "bass", "other")

STEM_LABELS_PT = {
    "lead": "Voz principal",
    "backing": "Backing vocals",
    "drums": "Bateria",
    "bass": "Baixo",
    "other": "Harmonia",
}

# What each Demucs output is called inside the file names audio-separator
# writes, and which of our stems it becomes.
BASE_OUTPUTS = {"drums": "drums", "bass": "bass", "other": "other"}


@dataclass
class StemFile:
    name: str
    path: Path
    bytes: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": STEM_LABELS_PT.get(self.name, self.name),
            "bytes": self.bytes,
        }


def _separator(output_dir: Path):
    """A configured audio-separator instance writing into ``output_dir``."""
    from audio_separator.separator import Separator

    STEM_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    return Separator(
        model_file_dir=str(STEM_MODEL_DIR),
        output_dir=str(output_dir),
        output_format=STEM_FORMAT,
        log_level=logging.WARNING,
    )


def _pick(outputs: list[str], keyword: str) -> Path | None:
    """The output whose file name carries ``keyword``.

    audio-separator names its files after the stem it believes it produced —
    ``…_(Vocals)_model.mp3`` and so on — so matching on the name is how the
    caller learns which file is which without depending on ordering.
    """
    for output in outputs:
        if keyword.lower() in Path(output).name.lower():
            return Path(output)
    return None


def separate(path: str | Path, song_id: str) -> list[StemFile]:
    """Separate one recording into the five stems, returning what was written.

    Raises ``RuntimeError`` when a stage produces nothing recognisable, rather
    than silently returning a shorter list: a mixer missing its lead vocal would
    look like a working feature that quietly cannot do the one thing it is for.
    """
    source = Path(path)
    destination = STEMS_DIR / song_id
    if destination.exists():
        shutil.rmtree(destination, ignore_errors=True)
    work = destination / "work"
    work.mkdir(parents=True, exist_ok=True)

    separator = _separator(work)

    logger.info("separating %s: stage 1 (%s)", song_id, STEM_MODEL_BASE)
    separator.load_model(model_filename=STEM_MODEL_BASE)
    base = [str(output) for output in separator.separate(str(source))]
    base = [str(work / Path(name).name) if not Path(name).is_absolute() else name for name in base]

    vocals = _pick(base, "vocals")
    if vocals is None:
        raise RuntimeError(
            f"{STEM_MODEL_BASE} produced no vocal stem (got: {[Path(p).name for p in base]})"
        )

    logger.info("separating %s: stage 2 (%s)", song_id, STEM_MODEL_KARAOKE)
    separator.load_model(model_filename=STEM_MODEL_KARAOKE)
    split = [str(output) for output in separator.separate(str(vocals))]
    split = [str(work / Path(name).name) if not Path(name).is_absolute() else name for name in split]

    # On a karaoke model the "vocals" output is the lead and the "instrumental"
    # output is what was left of the vocal stem — the backing voices.
    lead = _pick(split, "vocals")
    backing = _pick(split, "instrumental")
    if lead is None or backing is None:
        raise RuntimeError(
            f"{STEM_MODEL_KARAOKE} did not split lead from backing "
            f"(got: {[Path(p).name for p in split]})"
        )

    produced: dict[str, Path] = {"lead": lead, "backing": backing}
    for name, keyword in BASE_OUTPUTS.items():
        found = _pick(base, keyword)
        if found is not None:
            produced[name] = found

    written: list[StemFile] = []
    for name in STEM_NAMES:
        origin = produced.get(name)
        if origin is None or not origin.exists():
            continue
        target = destination / f"{name}.{STEM_FORMAT}"
        shutil.move(str(origin), target)
        written.append(StemFile(name=name, path=target, bytes=target.stat().st_size))

    shutil.rmtree(work, ignore_errors=True)
    logger.info("separated %s into %s", song_id, [stem.name for stem in written])
    return written


def stem_path(song_id: str, name: str) -> Path | None:
    """Path of one stored stem, or ``None`` when it was never produced."""
    if name not in STEM_NAMES:
        return None
    candidate = STEMS_DIR / song_id / f"{name}.{STEM_FORMAT}"
    return candidate if candidate.exists() else None


def available_stems(song_id: str) -> list[StemFile]:
    found: list[StemFile] = []
    for name in STEM_NAMES:
        path = stem_path(song_id, name)
        if path is not None:
            found.append(StemFile(name=name, path=path, bytes=path.stat().st_size))
    return found


def delete_stems(song_id: str) -> None:
    shutil.rmtree(STEMS_DIR / song_id, ignore_errors=True)


def load_stem_mono(song_id: str, names: list[str], sr: int):
    """Sum one or more stems back to mono at ``sr``, for feeding an analyser.

    Returns ``None`` when none of the requested stems exist, so every caller can
    fall back to the original mix without special-casing.
    """
    import librosa
    import numpy as np

    present = [path for path in (stem_path(song_id, name) for name in names) if path is not None]
    if not present:
        return None

    mixed = None
    for path in present:
        audio, _ = librosa.load(str(path), sr=sr, mono=True)
        if mixed is None:
            mixed = audio
            continue
        length = min(len(mixed), len(audio))
        mixed = mixed[:length] + audio[:length]

    if mixed is None:
        return None
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    return (mixed / peak).astype(np.float32) if peak > 0 else mixed
