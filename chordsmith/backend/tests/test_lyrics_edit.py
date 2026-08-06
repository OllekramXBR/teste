"""Tests for correcting a transcription by hand.

The recogniser is never going to be perfect, so the thing that has to be
trustworthy is the correction: the words a person typed must survive, and the
clock they are sung on must stay close enough for the karaoke highlight to
still track the voice.
"""

from __future__ import annotations

import pytest

from app.analysis.lyrics import rebuild_from_segments


def line(text: str, start: float, end: float) -> dict:
    return {"text": text, "start": start, "end": end}


class TestRebuild:
    def test_the_typed_words_are_what_comes_back(self):
        result = rebuild_from_segments([line("mil invernos no peito", 0.0, 2.0)])
        assert [word["text"] for word in result["words"]] == ["mil", "invernos", "no", "peito"]

    def test_words_stay_inside_their_line(self):
        result = rebuild_from_segments([line("uma frase curta", 4.0, 6.0)])
        assert result["words"][0]["start"] == pytest.approx(4.0)
        assert result["words"][-1]["end"] == pytest.approx(6.0, abs=0.01)

    def test_words_do_not_overlap_and_run_in_order(self):
        result = rebuild_from_segments([line("a bb ccc dddd", 0.0, 4.0)])
        times = result["words"]
        for earlier, later in zip(times, times[1:]):
            assert earlier["end"] <= later["start"] + 1e-6

    def test_a_longer_word_gets_a_longer_slot(self):
        # Not sample accurate, but closer to how the line is actually sung than
        # dividing it equally would be.
        words = rebuild_from_segments([line("oi coração", 0.0, 2.0)])["words"]
        short = words[0]["end"] - words[0]["start"]
        long = words[1]["end"] - words[1]["start"]
        assert long > short

    def test_two_lines_keep_their_own_spans(self):
        result = rebuild_from_segments(
            [line("primeira frase", 0.0, 1.0), line("segunda frase", 5.0, 6.0)]
        )
        assert result["segments"][1]["start"] == 5.0
        assert all(word["start"] >= 5.0 for word in result["words"][2:])

    def test_edited_words_are_never_dimmed_as_uncertain(self):
        # The karaoke view fades words the model doubted; a word a person typed
        # is not in doubt.
        result = rebuild_from_segments([line("punho fechado", 0.0, 1.0)])
        assert all(word["probability"] == 1.0 for word in result["words"])

    def test_the_result_is_marked_as_edited(self):
        assert rebuild_from_segments([line("qualquer coisa", 0.0, 1.0)])["edited"] is True

    def test_metadata_from_the_transcription_survives(self):
        previous = {"language": "pt", "model": "small", "audioSeconds": 227.9}
        result = rebuild_from_segments([line("nova letra", 0.0, 1.0)], previous)
        assert result["language"] == "pt"
        assert result["model"] == "small"
        assert result["audioSeconds"] == 227.9

    def test_blank_lines_are_dropped_rather_than_becoming_empty_words(self):
        result = rebuild_from_segments([line("   ", 0.0, 1.0), line("real", 1.0, 2.0)])
        assert len(result["segments"]) == 1
        assert result["wordCount"] == 1

    def test_a_line_with_no_duration_does_not_divide_by_zero(self):
        result = rebuild_from_segments([line("instantanea", 3.0, 3.0)])
        assert result["words"][0]["start"] == result["words"][0]["end"] == 3.0

    def test_an_end_before_its_start_is_clamped(self):
        result = rebuild_from_segments([line("invertida", 5.0, 2.0)])
        assert result["words"][0]["end"] >= result["words"][0]["start"]

    def test_an_empty_edit_produces_an_empty_lyric_rather_than_an_error(self):
        result = rebuild_from_segments([])
        assert result["words"] == [] and result["wordCount"] == 0
