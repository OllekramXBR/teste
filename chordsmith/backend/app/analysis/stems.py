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

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .. import progress
from ..config import (
    SEPARATION_TIMEOUT,
    SEPARATOR_BIN,
    STEM_FORMAT,
    STEM_MODEL_DIR,
    STEMS_DIR,
    stem_models,
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

# The separator reports itself through tqdm, which writes "  47%|####…". The
# last match on a piece wins, since one redraw can carry several numbers.
PERCENT = re.compile(r"(\d{1,3})%")

# A tqdm redraw ends in a carriage return, a real log line in a newline, and
# either one means: that piece is complete, parse it.
LINE_BREAK = re.compile("[\\r\\n]+")


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


def _run_separator(
    source: Path,
    model: str,
    output_dir: Path,
    names: dict[str, str],
    on_progress: Callable[[float], None] | None = None,
) -> list[str]:
    """Run one separation pass in the separator's own interpreter.

    A subprocess rather than an import, and the reason is not style. The
    separation stack pulls in torch and scikit-learn, and in the same
    interpreter as numba and librosa they fight over the OpenMP runtime until
    the analysis pipeline segfaults. Out here none of it is ever loaded into the
    API process, a crash in the model cannot take the server down, and the
    memory goes back to the machine when the process exits.

    ``names`` maps the model's own stem names to the file names we want, so the
    caller does not have to guess which output is which.
    """
    STEM_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    command = [
        str(SEPARATOR_BIN),
        str(source),
        "-m",
        model,
        "--output_dir",
        str(output_dir),
        "--output_format",
        STEM_FORMAT.upper(),
        "--model_file_dir",
        str(STEM_MODEL_DIR),
        "--custom_output_names",
        json.dumps(names),
    ]

    before = {path.name for path in output_dir.iterdir()} if output_dir.exists() else set()

    # Streamed rather than captured whole, so the percentage the separator
    # prints reaches the progress bar while it still means something. Captured
    # output only arrives when the process ends, which is precisely when nobody
    # needs to know how far along it was.
    #
    # Bytes, not text, and read with ``read1``. All three of the obvious ways to
    # read this pipe block until the end, for different reasons:
    #
    #   * ``for line in stdout`` waits for a newline, and tqdm redraws its bar
    #     with a carriage return and no newline.
    #   * ``read(n)`` on a text stream waits until it has *n* characters, and a
    #     redraw is about thirty.
    #
    # ``read1`` returns whatever has arrived. Measured with a stand-in that
    # writes like tqdm: with the other two, five updates spread over 0.75s all
    # surfaced in the same instant at the end.
    #
    # Default buffering, not ``bufsize=0``: unbuffered hands back a raw FileIO,
    # which has no ``read1`` at all.
    tail: list[str] = []
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        assert process.stdout is not None
        buffer = ""
        while True:
            raw = process.stdout.read1(4096)
            if not raw:
                break
            buffer += raw.decode("utf-8", errors="replace")
            pieces = LINE_BREAK.split(buffer)
            buffer = pieces.pop()  # whatever is left is still being written
            for piece in pieces:
                piece = piece.strip()
                if not piece:
                    continue
                tail.append(piece)
                del tail[:-40]  # only the end matters, and only if it fails
                if on_progress:
                    found = PERCENT.findall(piece)
                    if found:
                        on_progress(int(found[-1]) / 100)
        if buffer.strip():
            tail.append(buffer.strip())
        process.wait(timeout=SEPARATION_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
        raise

    if process.returncode != 0:
        raise RuntimeError(f"{model} failed: {_explain(tail)}")

    written = [
        str(path) for path in sorted(output_dir.iterdir()) if path.name not in before
    ]
    if not written:
        raise RuntimeError(f"{model} wrote no files")
    return written


def _explain(tail: list[str]) -> str:
    """Turn the separator's last output into something worth storing.

    This used to keep the final line and nothing else, which cost a real
    diagnosis: twenty-five separations failed with the separator's own
    "Separation produced no output files — see errors above" and the errors
    above had already been thrown away. The last line of a failure is almost
    never the reason for it.

    Progress redraws are dropped — a bar frozen at 82% says when it stopped, not
    why — and what is left is read newest-first for a line that names a cause.
    """
    real = [line for line in tail if line.strip() and not PERCENT.search(line)]
    if not real:
        return "no output from the separator"

    causes = ("error", "exception", "traceback", "memory", "killed", "no such", "not found")
    for line in reversed(real):
        lowered = line.lower()
        if any(word in lowered for word in causes) and "see errors above" not in lowered:
            return line[:400]
    # Nothing self-identifies as the cause, so hand back the closing lines
    # rather than one of them and let a person read the sequence.
    return " | ".join(real[-4:])[:400]


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


def separate(path: str | Path, song_id: str, quality: str | None = None) -> list[StemFile]:
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

    mix_model, karaoke_model = stem_models(quality)

    logger.info("separating %s: stage 1 (%s)", song_id, mix_model)
    progress.stage(song_id, "stems", "separando voz, bateria, baixo e harmonia", step=1)
    base = _run_separator(
        source,
        mix_model,
        work,
        {"Vocals": "mixed-vocals", "Drums": "drums", "Bass": "bass", "Other": "other"},
        on_progress=lambda fraction: progress.advance(song_id, "stems", fraction),
    )

    vocals = _pick(base, "vocals")
    if vocals is None:
        raise RuntimeError(
            f"{mix_model} produced no vocal stem (got: {[Path(p).name for p in base]})"
        )

    logger.info("separating %s: stage 2 (%s)", song_id, karaoke_model)
    progress.stage(song_id, "stems", "separando a voz principal dos backings", step=2)
    split = _run_separator(
        vocals,
        karaoke_model,
        work,
        {"Vocals": "lead", "Instrumental": "backing"},
        on_progress=lambda fraction: progress.advance(song_id, "stems", fraction),
    )

    # On a karaoke model the "vocals" output is the lead and the "instrumental"
    # output is what was left of the vocal stem — the backing voices.
    lead = _pick(split, "lead") or _pick(split, "vocals")
    backing = _pick(split, "backing") or _pick(split, "instrumental")

    produced: dict[str, Path] = {}
    if lead is not None and backing is not None:
        produced["lead"] = lead
        produced["backing"] = backing
    else:
        # The separator skips writing a stem it judges near-silent, so a missing
        # output is an answer rather than a fault: on an instrumental there is
        # no lead vocal to find, and on a track sung by one person alone there
        # are no backing voices. Failing the whole separation over that would
        # throw away four perfectly good stems to punish a song for its
        # arrangement. The vocal stem is kept whole as the lead instead, which
        # is what "mute the voice" should do when there is only one voice.
        logger.info(
            "%s produced only %s for %s; keeping the vocal stem whole as the lead",
            karaoke_model,
            [Path(p).name for p in split] or "nothing",
            song_id,
        )
        #
        # Only the whole stem, never it *and* one of the halves: whatever the
        # model did write is made of the same audio, so keeping both would put
        # those samples in the mix twice and the five stems would no longer sum
        # back to the recording.
        produced["lead"] = vocals
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
