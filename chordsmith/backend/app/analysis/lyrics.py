"""Sung-lyric transcription, with a word-level clock so chords can be placed.

Whisper (through faster-whisper's CTranslate2 runtime) does the recognition. Two
choices here are worth stating, because both were made to fit what the rest of
this app already assumes.

*The audio is handed over as a numpy array, never as a path.* faster-whisper
will happily open a file itself, but it does that with PyAV, and this image has
no ffmpeg — the whole app decodes through libsndfile via librosa. Resampling to
the 16 kHz Whisper wants and passing the samples straight in keeps one decoder
in the project instead of two.

*Word timestamps are not optional here.* A lyric sheet only needs segments, but
a cifra needs to know which syllable a chord change lands on, and that is a
word-level question.

What this does **not** do is separate the vocal from the band. There is no
source separation in this project, so a dense mix is transcribed with the
guitars still in it, and the result degrades accordingly. Sparse arrangements —
voice and one instrument — are where this is worth reading.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np

from ..config import (
    ASR_BEAM_SIZE,
    ASR_COMPUTE_TYPE,
    ASR_LANGUAGE,
    ASR_MODEL,
    ASR_MODEL_DIR,
    ASR_THREADS,
)

logger = logging.getLogger(__name__)

# Whisper's fixed input rate. Anything else is resampled before it goes in.
ASR_SR = 16000

# Words shorter than this are almost always the tail of a hallucination — a
# repeated article, a stray "e" — and they push real words out of alignment.
MIN_WORD_SECONDS = 0.02

_model = None
_model_lock = threading.Lock()


@dataclass
class TranscribedWord:
    text: str
    start: float
    end: float
    probability: float


def get_model():
    """Load the model once per process.

    The first call downloads the weights into the data volume, so a rebuilt
    container does not fetch them again.
    """
    global _model
    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            ASR_MODEL_DIR.mkdir(parents=True, exist_ok=True)
            logger.info("loading ASR model %s (%s)", ASR_MODEL, ASR_COMPUTE_TYPE)
            _model = WhisperModel(
                ASR_MODEL,
                device="cpu",
                compute_type=ASR_COMPUTE_TYPE,
                cpu_threads=ASR_THREADS,
                download_root=str(ASR_MODEL_DIR),
            )
        return _model


def to_asr_audio(y: np.ndarray, sr: int) -> np.ndarray:
    """Mono float32 at 16 kHz, which is the only shape the model accepts."""
    import librosa

    audio = np.asarray(y, dtype=np.float32)
    if audio.ndim > 1:
        audio = librosa.to_mono(audio)
    if sr != ASR_SR:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=ASR_SR)
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio / peak
    return audio.astype(np.float32)


def transcribe(
    y: np.ndarray,
    sr: int,
    *,
    language: str | None = None,
    model_name: str | None = None,
) -> dict:
    """Transcribe sung audio into words with times.

    ``model_name`` is accepted so a caller can compare sizes without restarting
    the process; leaving it unset uses the configured default and the cached
    model.
    """
    audio = to_asr_audio(y, sr)
    if audio.size < ASR_SR:  # under a second: nothing to hear
        return {
            "language": language or ASR_LANGUAGE,
            "model": model_name or ASR_MODEL,
            "words": [],
            "segments": [],
            "audioSeconds": round(float(audio.size / ASR_SR), 2),
        }

    if model_name and model_name != ASR_MODEL:
        from faster_whisper import WhisperModel

        model = WhisperModel(
            model_name,
            device="cpu",
            compute_type=ASR_COMPUTE_TYPE,
            cpu_threads=ASR_THREADS,
            download_root=str(ASR_MODEL_DIR),
        )
    else:
        model = get_model()

    segments, info = model.transcribe(
        audio,
        language=language or ASR_LANGUAGE or None,
        beam_size=ASR_BEAM_SIZE,
        word_timestamps=True,
        # Music is mostly not speech, and without a voice gate Whisper invents
        # words over instrumental passages — the classic looping hallucination.
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 700},
        condition_on_previous_text=False,
    )

    words: list[dict] = []
    lines: list[dict] = []
    for segment in segments:
        text = (segment.text or "").strip()
        if text:
            lines.append(
                {
                    "start": round(float(segment.start), 3),
                    "end": round(float(segment.end), 3),
                    "text": text,
                }
            )
        for word in segment.words or []:
            cleaned = (word.word or "").strip()
            if not cleaned or float(word.end) - float(word.start) < MIN_WORD_SECONDS:
                continue
            words.append(
                {
                    "text": cleaned,
                    "start": round(float(word.start), 3),
                    "end": round(float(word.end), 3),
                    "probability": round(float(word.probability), 3),
                }
            )

    words.sort(key=lambda item: item["start"])
    return {
        "language": getattr(info, "language", language or ASR_LANGUAGE),
        "languageProbability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 3),
        "model": model_name or ASR_MODEL,
        "words": words,
        "segments": lines,
        "wordCount": len(words),
        "audioSeconds": round(float(audio.size / ASR_SR), 2),
    }


def transcribe_file(path, **kwargs) -> dict:
    """Convenience wrapper that loads the audio through the project's decoder."""
    from .pipeline import load_audio

    y, sr = load_audio(path, sr=ASR_SR)
    return transcribe(y, sr, **kwargs)
