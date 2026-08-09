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
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

_WORD_CLEAN = re.compile(r"[^\wÀ-ſ]+", re.UNICODE)


def _norm(word: str) -> str:
    return _WORD_CLEAN.sub("", word.lower())


def align_chart_lyrics(words: list[dict], chart_lines: list[str]) -> list[dict]:
    """Chart lines with times, as ``{start, end, text}`` segments.

    ``words`` are the transcription's words (``text``/``start``/``end``);
    ``chart_lines`` are the verse lines of the imported chart, in order.
    Returns one segment per non-empty chart line. Raises ``ValueError`` when
    there is nothing to align on either side.
    """
    lines = [line.strip() for line in chart_lines if line and line.strip()]
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

    return segments
