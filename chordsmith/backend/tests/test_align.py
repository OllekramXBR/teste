"""The chart-to-clock alignment: right words, sung times, named sections."""

import pytest

from app.analysis.align import align_chart_lyrics, apply_chart, split_markers


def _words(pairs):
    return [
        {"text": text, "start": float(start), "end": float(start) + 0.4, "probability": 0.9}
        for text, start in pairs
    ]


def test_matched_lines_take_their_sung_times():
    words = _words(
        [("olha", 10.0), ("que", 10.5), ("coisa", 11.0), ("mais", 11.5), ("linda", 12.0),
         ("cheia", 20.0), ("de", 20.4), ("graça", 20.8)]
    )
    lines = ["Olha que coisa mais linda", "Cheia de graça"]
    segments, sections = align_chart_lyrics(words, lines)

    assert [segment["text"] for segment in segments] == lines
    assert segments[0]["start"] == pytest.approx(10.0)
    assert segments[0]["end"] == pytest.approx(12.4)
    assert segments[1]["start"] == pytest.approx(20.0)
    assert sections == []


def test_misheard_words_still_anchor_on_the_rest():
    # The model heard "coija" for "coisa": the line still lands on its time
    # because the other words match.
    words = _words(
        [("olha", 5.0), ("que", 5.4), ("coija", 5.8), ("mais", 6.2), ("linda", 6.6),
         ("cheia", 9.0), ("de", 9.3), ("graça", 9.6)]
    )
    lines = ["Olha que coisa mais linda", "Cheia de graça"]
    segments, _ = align_chart_lyrics(words, lines)
    assert segments[0]["start"] == pytest.approx(5.0)
    assert segments[1]["start"] == pytest.approx(9.0)


def test_unheard_line_is_interpolated_between_neighbours():
    words = _words(
        [("primeira", 2.0), ("linha", 2.5), ("cantada", 3.0),
         ("terceira", 30.0), ("linha", 30.5), ("cantada", 31.0)]
    )
    lines = ["Primeira linha cantada", "Segunda que ninguém ouviu", "Terceira linha cantada"]
    segments, _ = align_chart_lyrics(words, lines)
    assert len(segments) == 3
    middle = segments[1]
    assert segments[0]["end"] <= middle["start"] < middle["end"] <= segments[2]["start"] + 0.01
    assert middle["text"] == "Segunda que ninguém ouviu"


def test_bracketed_markers_become_sections_on_the_next_line_time():
    words = _words(
        [("olha", 8.0), ("que", 8.4), ("coisa", 8.8), ("mais", 9.2), ("linda", 9.6),
         ("cheia", 40.0), ("de", 40.4), ("graça", 40.8)]
    )
    lines = [
        "[Primeira Parte]",
        "Olha que coisa mais linda",
        "[Refrão]",
        "Cheia de graça",
    ]
    segments, sections = align_chart_lyrics(words, lines)

    # Markers are not sung lines.
    assert [segment["text"] for segment in segments] == [
        "Olha que coisa mais linda",
        "Cheia de graça",
    ]
    assert [section["name"] for section in sections] == ["Primeira Parte", "Refrão"]
    assert sections[0]["start"] == pytest.approx(8.0)
    assert sections[1]["start"] == pytest.approx(40.0)


def test_trailing_marker_clamps_to_the_last_line():
    words = _words([("única", 3.0), ("linha", 3.5), ("cantada", 4.0), ("aqui", 4.5)])
    lines = ["Única linha cantada aqui", "[Final]"]
    segments, sections = align_chart_lyrics(words, lines)
    assert len(segments) == 1
    assert sections[0]["name"] == "Final"
    assert sections[0]["start"] == segments[0]["start"]


def test_split_markers_keeps_order_and_indexes():
    sung, markers = split_markers(["[Intro]", "Linha um", "", "[Refrão]:", "Linha dois"])
    assert sung == ["Linha um", "Linha dois"]
    assert markers == [(0, "Intro"), (1, "Refrão")]


def test_apply_chart_flags_and_sections():
    words = _words(
        [("olha", 8.0), ("que", 8.4), ("coisa", 8.8), ("mais", 9.2), ("linda", 9.6),
         ("cheia", 40.0), ("de", 40.4), ("graça", 40.8)]
    )
    lyrics = {"words": words, "segments": [], "model": "medium", "wordCount": len(words)}
    chart = {
        "lines": [
            {"kind": "verse", "text": "[Refrão]", "chords": []},
            {"kind": "verse", "text": "Olha que coisa mais linda", "chords": []},
            {"kind": "tab", "text": "e|----", "chords": []},
            {"kind": "verse", "text": "Cheia de graça", "chords": []},
        ]
    }
    result = apply_chart(lyrics, chart)
    assert result["correctedByChart"] is True
    assert result["edited"] is True
    assert [section["name"] for section in result["sections"]] == ["Refrão"]
    assert result["segments"][0]["text"] == "Olha que coisa mais linda"


def test_wrong_song_is_refused():
    words = _words([("completamente", 1.0), ("outra", 1.5), ("gravação", 2.0), ("aqui", 2.5)])
    lines = ["Nada disso aparece", "Na letra da cifra importada", "Nem uma palavra bate"]
    with pytest.raises(ValueError):
        align_chart_lyrics(words, lines)


def test_empty_sides_are_refused():
    with pytest.raises(ValueError):
        align_chart_lyrics([], ["Uma linha"])
    with pytest.raises(ValueError):
        align_chart_lyrics(_words([("oi", 1.0)]), [])
    with pytest.raises(ValueError):
        align_chart_lyrics(_words([("oi", 1.0)]), ["[Refrão]"])
