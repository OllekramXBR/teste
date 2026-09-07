"""Marry the written lyric to the sung clock.

The web chart knows the *words* — a person typed them. The transcription
knows the *times* — the model heard them. Neither is whole: the chart has no
clock and the transcription mishears. This module aligns the two so the
karaoke view can show the chart's words at the transcription's times.

The alignment is word-level ``SequenceMatcher`` over normalised tokens:
accents kept (Portuguese), case and punctuation dropped. Chart lines then
take their start from the first matched word and their end from the last;
lines with no match at all — a bridge the singer skipped, a mishearing so
complete nothing survived — are interpolated between their timed neighbours
rather than dropped, because a lyric line with a slightly wrong time is
usable on stage and a missing one is not.

Chart lines written in brackets — ``[Intro]``, ``[Refrão]``, ``[Primeira
Parte]`` — are not lyric at all: they are the song's structure. They come out
separately as sections, each anchored to the start of the first sung line
that follows it, which is what lets the app offer "repeat the chorus" instead
of "repeat bars 17 to 24".
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

_WORD_CLEAN = re.compile(r"[^\wÀ-ſ]+", re.UNICODE)

# A whole line inside square brackets is a section marker on Cifra Club.
_SECTION = re.compile(r"^\[\s*([^\]]{1,48}?)\s*\]:?$")


def _norm(word: str) -> str:
    return _WORD_CLEAN.sub("", word.lower())


def split_markers(chart_lines: list[str]) -> tuple[list[str], list[tuple[int, str]]]:
    """Sung lines, and ``(sung_line_index, name)`` for each section marker.

    The index is the position *in the sung list* of the first line after the
    marker, so a marker anchors to whatever gets sung next. Markers at the
    very end (nothing sung after them) are kept and anchored past the last
    line; the caller clamps them.
    """
    sung: list[str] = []
    markers: list[tuple[int, str]] = []
    for raw in chart_lines:
        line = (raw or "").strip()
        if not line:
            continue
        match = _SECTION.match(line)
        if match:
            markers.append((len(sung), match.group(1)))
        else:
            sung.append(line)
    return sung, markers


def align_chart_lyrics(
    words: list[dict], chart_lines: list[str]
) -> tuple[list[dict], list[dict]]:
    """``(segments, sections)`` for the chart sung against this recording.

    ``words`` are the transcription's words (``text``/``start``/``end``);
    ``chart_lines`` are the verse lines of the imported chart, in order,
    section markers included. Segments are ``{start, end, text}``, one per
    sung line; sections are ``{name, start}``. Raises ``ValueError`` when
    there is nothing to align or too little matches to be the same song.
    """
    lines, markers = split_markers(chart_lines)
    if not lines:
        raise ValueError("the chart has no lyric lines")
    if not words:
        raise ValueError("the transcription has no words to take times from")

    # Flatten the chart to words, remembering which line each came from.
    chart_words: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        for piece in line.split():
            if _norm(piece):
                chart_words.append((index, piece))
    if not chart_words:
        raise ValueError("the chart has no alignable words")

    heard = [_norm(word["text"]) for word in words]
    written = [_norm(piece) for _, piece in chart_words]

    # autojunk off: repeated words ("amor", "não") are the norm in a lyric,
    # and autojunk would demote exactly the anchors we need.
    matcher = SequenceMatcher(None, heard, written, autojunk=False)

    # For each chart line: the times of its matched words.
    line_start: dict[int, float] = {}
    line_end: dict[int, float] = {}
    matched = 0
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            word = words[block.a + offset]
            line_index = chart_words[block.b + offset][0]
            start = float(word["start"])
            end = float(word["end"])
            if line_index not in line_start or start < line_start[line_index]:
                line_start[line_index] = start
            if line_index not in line_end or end > line_end[line_index]:
                line_end[line_index] = end
            matched += 1

    # Too few anchors means the songs simply do not match (wrong chart, or a
    # transcription of another take); a bad alignment is worse than none.
    if matched < max(4, len(written) // 10):
        raise ValueError(
            f"only {matched} of {len(written)} chart words were heard in the "
            "recording — the chart and the audio do not seem to be the same song"
        )

    # Interpolate the unmatched lines: each consecutive run of them divides
    # the silence between its timed neighbours into equal shares.
    segments: list[dict] = []
    total = len(lines)
    index = 0
    while index < total:
        if index in line_start:
            index += 1
            continue
        run = [index]
        while run[-1] + 1 < total and run[-1] + 1 not in line_start:
            run.append(run[-1] + 1)
        previous_end = max(
            (line_end[i] for i in line_end if i < run[0]),
            default=float(words[0]["start"]),
        )
        next_start = min(
            (line_start[i] for i in line_start if i > run[-1]),
            default=float(words[-1]["end"]),
        )
        span = max(next_start - previous_end, 0.5 * len(run))
        share = span / len(run)
        for position, line_index in enumerate(run):
            line_start[line_index] = previous_end + position * share
            line_end[line_index] = previous_end + (position + 1) * share
        index = run[-1] + 1

    for index, text in enumerate(lines):
        start = line_start[index]
        end = max(line_end[index], start + 0.4)
        segments.append({"start": round(start, 3), "end": round(end, 3), "text": text})

    # Times must never run backwards, whatever the matcher thought it heard.
    for previous, current in zip(segments, segments[1:]):
        if current["start"] < previous["start"]:
            current["start"] = previous["start"]
        if current["end"] < current["start"]:
            current["end"] = current["start"] + 0.4

    # Sections anchor to the first sung line at or after their marker; a
    # marker with nothing sung after it points at the last line instead of
    # falling off the end. Consecutive markers at one spot keep the last name
    # ("[Solo]" directly followed by "[Refrão]" is a chorus for our purposes).
    sections: list[dict] = []
    for line_index, name in markers:
        anchored = segments[min(line_index, len(segments) - 1)]
        entry = {"name": name, "start": anchored["start"]}
        if sections and sections[-1]["start"] == entry["start"]:
            sections[-1] = entry
        else:
            sections.append(entry)

    return segments, sections


def apply_chart(lyrics: dict, chart: dict) -> dict:
    """An aligned copy of ``lyrics``: the chart's words, the sung clock.

    Shared by the align endpoint and the transcription job, so a manual
    "Sincronizar" and the automatic pass after transcription can never
    disagree about what alignment means. Raises ``ValueError`` like
    :func:`align_chart_lyrics` when the two sides do not fit.
    """
    from .lyrics import rebuild_from_segments

    verse_lines = [
        line["text"] for line in chart.get("lines", []) if line.get("kind") == "verse"
    ]
    segments, sections = align_chart_lyrics(lyrics.get("words") or [], verse_lines)
    result = rebuild_from_segments(segments, previous=lyrics)
    result["correctedByChart"] = True
    result["sections"] = sections
    return result
