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

from . import progress, storage
from .config import ANALYSIS_WORKERS, AUDIO_DIR, AUTO_LYRICS, AUTO_STEMS

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
        _continue_after_analysis(song_id, path)
    except Exception as exc:  # noqa: BLE001 - surfaced to the client verbatim
        logger.exception("analysis failed for %s", song_id)
        storage.set_status(song_id, "failed", error=str(exc))


def _run_lyrics(song_id: str, path: Path, model_name: str | None) -> None:
    from .analysis.lyrics import transcribe_file

    try:
        storage.set_lyrics_status(song_id, "transcribing")
        progress.start(song_id, "lyrics")
        progress.stage(song_id, "lyrics", "ouvindo a voz")
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
    finally:
        progress.finish(song_id, "lyrics")


def _continue_after_analysis(song_id: str, path: Path) -> None:
    """Keep going without being asked: lyric, then stems, then per-stem notes.

    Every step is minutes long and every one is wanted eventually, so waiting
    for a click only buys that the work happens while somebody is watching
    instead of while they are not. Anything already done is skipped, so this
    stays safe to reach on a re-analysis.
    """
    from .analysis import stems as stem_module

    song = storage.get_song(song_id, include_analysis=False)
    if not song:
        return

    try:
        if AUTO_LYRICS and song["lyricsStatus"] in ("none", "failed"):
            enqueue_lyrics(song_id, path.name)
        if AUTO_STEMS and not stem_module.available_stems(song_id):
            if song["stemsStatus"] not in ("pending", "separating"):
                enqueue_stems(song_id, path.name)
    except RuntimeError:
        # The pool refuses new work once the interpreter is shutting down. A
        # song that finished its analysis exactly as the server stopped is a
        # real race, not only a test artefact, and the follow-up work is picked
        # up again on the next start — losing it is not worth crashing the
        # analysis that already succeeded.
        logger.info("not queueing follow-up work for %s: shutting down", song_id)


def enqueue(song_id: str, filename: str) -> None:
    get_executor().submit(_run_analysis, song_id, AUDIO_DIR / filename)


def _run_stems(song_id: str, path: Path, quality: str | None = None) -> None:
    from .analysis.stems import separate

    try:
        storage.set_stems_status(song_id, "separating")
        # Two model passes, which is what the bar divides itself into.
        progress.start(song_id, "stems", steps=2)
        started = time.perf_counter()
        written = separate(path, song_id, quality=quality)
        storage.set_stems_status(song_id, "ready")
        logger.info(
            "separated %s into %d stems in %.1fs",
            song_id,
            len(written),
            time.perf_counter() - started,
        )
        # The tablature and the notation both read this, so it follows straight
        # on rather than waiting for someone to open the view that needs it.
        try:
            enqueue_multitrack(song_id)
        except RuntimeError:
            # Same shutdown race as after the analysis: the separation itself
            # succeeded and its stems are on disk, so it must not be reported
            # as a failure because the follow-up could not be queued.
            logger.info("not queueing transcription for %s: shutting down", song_id)
    except Exception as exc:  # noqa: BLE001 - surfaced to the client verbatim
        logger.exception("separation failed for %s", song_id)
        storage.set_stems_status(song_id, "failed", error=str(exc))
    finally:
        progress.finish(song_id, "stems")


def enqueue_stems(song_id: str, filename: str, quality: str | None = None) -> None:
    """Queue a separation.

    Two model passes over the whole recording, on a CPU. Minutes, not seconds —
    which is exactly why it is asked for rather than done on upload.
    """
    storage.set_stems_status(song_id, "pending")
    progress.enqueued(song_id, "stems")
    get_heavy_executor().submit(_run_stems, song_id, AUDIO_DIR / filename, quality)


def _run_multitrack(song_id: str) -> None:
    import json

    from .analysis.multitrack import transcribe_song
    from .config import STEMS_DIR

    try:
        started = time.perf_counter()
        progress.start(song_id, "tracks")
        progress.stage(song_id, "tracks", "transcrevendo cada pista")
        tracks = transcribe_song(song_id)
        payload = [
            {
                "name": track.name,
                "program": track.program,
                "stem": track.stem,
                "notes": [
                    {
                        "midi": note.midi,
                        "start": round(note.start, 4),
                        "end": round(note.end, 4),
                        "velocity": round(note.velocity, 3),
                        "string": position[0] if position else None,
                        "fret": position[1] if position else None,
                    }
                    for note, position in zip(
                        track.notes, track.positions or [None] * len(track.notes)
                    )
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
    finally:
        progress.finish(song_id, "tracks")


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
    progress.enqueued(song_id, "lyrics")
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
    # Transcription and separation used to be marked failed here instead of
    # being picked up again, on the reasoning that they cost minutes and should
    # not repeat unasked. That reasoning belonged to a version where a person
    # clicked to start them. They now run automatically, and the consequence was
    # measurable: 40 songs sat marked "Interrupted by a restart" with no stems
    # and 38 with no lyrics, because every restart — and with --reload, every
    # save — emptied the queue instead of resuming it. Work nobody asked to
    # cancel is work to finish.
    for song_id in storage.stale_lyrics_ids():
        stored = storage.get_song_file(song_id)
        if not stored or not (AUDIO_DIR / stored[0]).exists():
            storage.set_lyrics_status(song_id, "failed", error="Audio file is missing")
            continue
        enqueue_lyrics(song_id, stored[0])
    for song_id in storage.stale_stems_ids():
        stored = storage.get_song_file(song_id)
        if not stored or not (AUDIO_DIR / stored[0]).exists():
            storage.set_stems_status(song_id, "failed", error="Audio file is missing")
            continue
        enqueue_stems(song_id, stored[0])
    return count


def retry_failed(kind: str = "both") -> dict[str, int]:
    """Queue everything a restart abandoned, and anything else that failed.

    A separation that died because the process went away is not a song the
    models cannot handle; it is a song they never finished trying. Kept separate
    from the startup path so it can also be pointed at the backlog that built up
    before restarts started resuming properly.
    """
    queued = {"lyrics": 0, "stems": 0}
    from .analysis import stems as stem_module

    for song in storage.list_songs(limit=1000):
        if song["status"] != "ready":
            continue
        stored = storage.get_song_file(song["id"])
        if not stored or not (AUDIO_DIR / stored[0]).exists():
            continue
        if kind in ("both", "lyrics") and song["lyricsStatus"] == "failed":
            enqueue_lyrics(song["id"], stored[0])
            queued["lyrics"] += 1
        if kind in ("both", "stems") and song["stemsStatus"] == "failed":
            if not stem_module.available_stems(song["id"]):
                enqueue_stems(song["id"], stored[0])
                queued["stems"] += 1
    logger.info("requeued %d lyrics and %d separations", queued["lyrics"], queued["stems"])
    return queued


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
