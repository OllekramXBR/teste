"""Background analysis queue.

Analysis is CPU-bound and takes seconds, so uploads return immediately and the
work happens on a small thread pool. The frontend polls the song until its
status flips from ``analyzing`` to ``ready`` or ``failed``.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import storage
from .config import ANALYSIS_WORKERS, AUDIO_DIR

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_heavy_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=ANALYSIS_WORKERS, thread_name_prefix="analysis"
            )
        return _executor


def get_heavy_executor() -> ThreadPoolExecutor:
    """A queue of its own for source separation.

    Separation takes minutes where analysis takes seconds, and both used to
    share a pool of two. One separation therefore held half the capacity, and
    two of them held all of it — a track uploaded in the meantime sat in the
    queue behind eight minutes of model inference for no reason.

    One worker, deliberately: the models are already using every core, so a
    second concurrent separation would not finish two jobs faster, it would
    just make the first one late.
    """
    global _heavy_executor
    with _executor_lock:
        if _heavy_executor is None:
            _heavy_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="separation")
        return _heavy_executor


def shutdown() -> None:
    global _executor, _heavy_executor
    with _executor_lock:
        for pool in (_executor, _heavy_executor):
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)
        _executor = None
        _heavy_executor = None


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


def _run_lyrics(song_id: str, path: Path, model_name: str | None) -> None:
    from .analysis.lyrics import transcribe_file

    try:
        storage.set_lyrics_status(song_id, "transcribing")
        started = time.perf_counter()
        result = transcribe_file(path, model_name=model_name)
        result["transcribeSeconds"] = round(time.perf_counter() - started, 2)
        storage.save_lyrics(song_id, result)
        logger.info(
            "transcribed %s: %d words in %.1fs",
            song_id,
            result.get("wordCount", 0),
            result["transcribeSeconds"],
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the client verbatim
        logger.exception("transcription failed for %s", song_id)
        storage.set_lyrics_status(song_id, "failed", error=str(exc))


def enqueue(song_id: str, filename: str) -> None:
    get_executor().submit(_run_analysis, song_id, AUDIO_DIR / filename)


def _run_stems(song_id: str, path: Path, quality: str | None = None) -> None:
    from .analysis.stems import separate

    try:
        storage.set_stems_status(song_id, "separating")
        started = time.perf_counter()
        written = separate(path, song_id, quality=quality)
        storage.set_stems_status(song_id, "ready")
        logger.info(
            "separated %s into %d stems in %.1fs",
            song_id,
            len(written),
            time.perf_counter() - started,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the client verbatim
        logger.exception("separation failed for %s", song_id)
        storage.set_stems_status(song_id, "failed", error=str(exc))


def enqueue_stems(song_id: str, filename: str, quality: str | None = None) -> None:
    """Queue a separation.

    Two model passes over the whole recording, on a CPU. Minutes, not seconds —
    which is exactly why it is asked for rather than done on upload.
    """
    storage.set_stems_status(song_id, "pending")
    get_heavy_executor().submit(_run_stems, song_id, AUDIO_DIR / filename, quality)


def _run_multitrack(song_id: str) -> None:
    import json

    from .analysis.multitrack import transcribe_song
    from .config import STEMS_DIR

    try:
        started = time.perf_counter()
        tracks = transcribe_song(song_id)
        payload = [
            {
                "name": track.name,
                "program": track.program,
                "notes": [
                    {
                        "midi": note.midi,
                        "start": round(note.start, 4),
                        "end": round(note.end, 4),
                        "velocity": round(note.velocity, 3),
                    }
                    for note in track.notes
                ],
            }
            for track in tracks
        ]
        destination = STEMS_DIR / song_id / "tracks.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload), encoding="utf-8")
        logger.info(
            "transcribed %d tracks for %s in %.1fs",
            len(payload),
            song_id,
            time.perf_counter() - started,
        )
    except Exception:  # noqa: BLE001 - reported through the missing cache file
        logger.exception("multitrack transcription failed for %s", song_id)


def _run_variant(song_id: str, semitones: int, rate: float) -> None:
    from .analysis.variants import render

    try:
        started = time.perf_counter()
        written = render(song_id, semitones, rate)
        logger.info(
            "rendered %d stems of %s at %+d semitones %.2fx in %.1fs",
            len(written),
            song_id,
            semitones,
            rate,
            time.perf_counter() - started,
        )
    except Exception:  # noqa: BLE001 - reported by the variant simply not appearing
        logger.exception("variant render failed for %s", song_id)


def enqueue_variant(song_id: str, semitones: int, rate: float) -> None:
    """Queue a transposed or time-stretched render of every stem."""
    get_heavy_executor().submit(_run_variant, song_id, semitones, rate)


def enqueue_multitrack(song_id: str) -> None:
    """Queue per-stem transcription.

    On the heavy queue with separation, because it is the same kind of work:
    minutes of signal processing that must not sit in front of a chord analysis
    someone is waiting on.
    """
    get_heavy_executor().submit(_run_multitrack, song_id)


def enqueue_all_stems() -> list[str]:
    """Queue separation for every analysed song that has none yet.

    The point is to be able to hand the library over and walk away: the queue is
    served one song at a time and survives the browser being closed, because it
    was never running there in the first place.
    """
    from .analysis import stems as stem_module

    queued: list[str] = []
    for song in storage.list_songs(limit=500):
        if song["status"] != "ready":
            continue
        if song["stemsStatus"] in ("pending", "separating"):
            continue
        if stem_module.available_stems(song["id"]):
            continue
        stored = storage.get_song_file(song["id"])
        if not stored or not (AUDIO_DIR / stored[0]).exists():
            continue
        enqueue_stems(song["id"], stored[0])
        queued.append(song["id"])
    logger.info("queued %d songs for separation", len(queued))
    return queued


def enqueue_lyrics(song_id: str, filename: str, model_name: str | None = None) -> None:
    """Queue a transcription.

    Kept off the upload path on purpose: recognising sung words costs minutes
    where the chord analysis costs seconds, and most of the app is usable
    without it. The user asks for lyrics when they want them.
    """
    storage.set_lyrics_status(song_id, "pending")
    get_executor().submit(_run_lyrics, song_id, AUDIO_DIR / filename, model_name)


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
    # A transcription killed mid-flight is not requeued — it costs minutes and
    # the user may not want it repeated on every restart — but it must not stay
    # stuck showing a spinner either.
    for song_id in storage.stale_lyrics_ids():
        storage.set_lyrics_status(song_id, "failed", error="Interrupted by a restart")
    for song_id in storage.stale_stems_ids():
        storage.set_stems_status(song_id, "failed", error="Interrupted by a restart")
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
