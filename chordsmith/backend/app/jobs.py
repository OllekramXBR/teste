"""Background analysis queue.

Analysis is CPU-bound and takes seconds, so uploads return immediately and the
work happens on a small thread pool. The frontend polls the song until its
status flips from ``analyzing`` to ``ready`` or ``failed``.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import storage
from .config import ANALYSIS_WORKERS, AUDIO_DIR

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=ANALYSIS_WORKERS, thread_name_prefix="analysis"
            )
        return _executor


def shutdown() -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def _run_analysis(song_id: str, path: Path) -> None:
    # Imported lazily: librosa pulls in numba and takes seconds to import, which
    # would otherwise be paid on every process start even for pure API use.
    from .analysis.pipeline import analyze_file

    try:
        storage.set_status(song_id, "analyzing")
        result = analyze_file(path)
        storage.save_analysis(song_id, result.to_dict())
        logger.info("analysed %s in %.2fs", song_id, result.analysis_seconds)
    except Exception as exc:  # noqa: BLE001 - surfaced to the client verbatim
        logger.exception("analysis failed for %s", song_id)
        storage.set_status(song_id, "failed", error=str(exc))


def enqueue(song_id: str, filename: str) -> None:
    get_executor().submit(_run_analysis, song_id, AUDIO_DIR / filename)


def requeue_incomplete() -> int:
    """Re-submit songs whose analysis was interrupted by a restart."""
    count = 0
    for song_id in storage.stale_processing_ids():
        song = storage.get_song(song_id, include_analysis=False)
        if not song:
            continue
        stored = storage.get_song_file(song_id)
        if not stored or not (AUDIO_DIR / stored[0]).exists():
            storage.set_status(song_id, "failed", error="Audio file is missing")
            continue
        enqueue(song_id, stored[0])
        count += 1
    return count


def warm_up() -> None:
    """Import librosa and trigger its numba JIT ahead of the first upload.

    Without this the first analysis pays ~30s of compilation; after it, the same
    track takes a couple of seconds.
    """

    def _warm() -> None:
        try:
            import numpy as np
            import librosa

            from .analysis import beats, chords
            from .analysis.pipeline import beat_synchronous_chroma

            sr = beats.DEFAULT_SR
            tone = np.sin(2 * np.pi * 220 * np.arange(sr * 2) / sr).astype(np.float32)
            harmonic, percussive = librosa.effects.hpss(tone)
            _, beat_times, _ = beats.track_beats(percussive, sr=sr)
            chroma, bass = beat_synchronous_chroma(harmonic, beat_times, sr)
            chords.decode(chroma, bass)
            logger.info("analysis engine warmed up")
        except Exception:  # noqa: BLE001 - warm-up is best effort
            logger.exception("warm-up failed")

    threading.Thread(target=_warm, name="warmup", daemon=True).start()
