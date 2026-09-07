"""Theory helpers exposed to the client: chord vocabulary, transpose, capo."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..analysis import theory

router = APIRouter(prefix="/api/theory", tags=["theory"])


@router.get("/vocabulary")
def vocabulary() -> dict:
    """Every chord the analyser can produce, with its pitch classes."""
    return {
        "qualities": [
            {"suffix": suffix, "intervals": list(intervals)}
            for suffix, intervals in theory.QUALITIES.items()
        ],
        "sharpNames": theory.SHARP_NAMES,
        "flatNames": theory.FLAT_NAMES,
        "chords": [
            chord.to_dict() for chord in theory.chord_vocabulary() if not chord.is_none
        ],
    }


@router.get("/transpose")
def transpose(
    labels: str = Query(..., description="Comma-separated chord labels"),
    semitones: int = Query(0, ge=-11, le=11),
    capo: int = Query(0, ge=0, le=11),
    flats: bool = Query(False),
) -> dict:
    """Transpose labels and optionally re-shape them for a capo position."""
    parsed = [label.strip() for label in labels.split(",") if label.strip()]
    if not parsed:
        raise HTTPException(status_code=400, detail="No chord labels supplied")

    transposed = [theory.transpose_label(label, semitones, flats) for label in parsed]
    shapes = theory.capo_shift(transposed, capo, flats) if capo else list(transposed)
    return {"sounding": transposed, "shapes": shapes, "capo": capo, "semitones": semitones}
