"""Tests for the Brazilian cifra renderer.

These use hand-built analysis dictionaries rather than the pipeline: the point
under test is the layout and the notation, and a synthetic chart makes the
expected column of every chord something the test can state exactly.
"""

from __future__ import annotations

import pytest

from app.analysis import cifra


def chord(label: str, start: float, end: float) -> dict:
    return {"label": label, "start": start, "end": end}


def word(text: str, start: float, end: float) -> dict:
    return {"text": text, "start": start, "end": end}


@pytest.fixture
def analysis() -> dict:
    return {
        "useFlats": False,
        "key": {"tonic": 7, "mode": "major", "name": "G major"},
        "beatsPerBar": 4,
        "beats": [
            {"index": index, "time": index * 0.5, "bar": index // 4 + 1, "beatInBar": index % 4 + 1}
            for index in range(16)
        ],
        "chords": [
            chord("G", 0.0, 2.0),
            chord("D", 2.0, 4.0),
            chord("Em", 4.0, 6.0),
            chord("C", 6.0, 8.0),
        ],
        "lead": {"sections": []},
    }


class TestNotation:
    @pytest.mark.parametrize(
        ("english", "brazilian"),
        [
            ("G", "G"),
            ("Gm", "Gm"),
            ("G7", "G7"),
            ("Gm7", "Gm7"),
            ("Gmaj7", "G7M"),
            ("Gdim", "G°"),
            ("Gdim7", "G°7"),
            ("Gaug", "G+"),
            ("Gm7b5", "Gm7(b5)"),
            ("Gsus4", "Gsus4"),
            ("F#m", "F#m"),
        ],
    )
    def test_quality_suffixes_follow_the_brazilian_convention(self, english, brazilian):
        assert cifra.br_label(english) == brazilian

    def test_flat_spelling_is_honoured(self):
        assert cifra.br_label("A#m7", use_flats=True) == "Bbm7"

    def test_no_chord_and_junk_survive_untouched(self):
        assert cifra.br_label("N") == "N"
        assert cifra.br_label("???") == "???"


class TestLayout:
    def test_chord_sits_above_the_word_it_lands_on(self, analysis):
        # One sung phrase: the words have to stay inside PHRASE_GAP of each
        # other or the renderer is right to split them across lines, and then
        # there is no single row to check the columns against.
        analysis["chords"] = [
            chord("G", 0.0, 0.5),
            chord("D", 0.5, 1.0),
            chord("Em", 1.0, 1.5),
            chord("C", 1.5, 2.0),
        ]
        lyrics = {
            "words": [
                word("um", 0.0, 0.4),
                word("dois", 0.5, 0.9),
                word("três", 1.0, 1.4),
                word("quatro", 1.5, 1.9),
            ]
        }
        text = cifra.render(analysis, lyrics)
        chord_row, lyric_row = _first_pair(text)

        for label, target in (("G", "um"), ("D", "dois"), ("Em", "três"), ("C", "quatro")):
            assert chord_row.index(label) == lyric_row.index(target), (
                f"{label} is not above {target}\n{chord_row}\n{lyric_row}"
            )

    def test_labels_never_collide(self, analysis):
        # Four changes inside one short word: they cannot all sit above it, so
        # they must at least stay readable and in order.
        analysis["chords"] = [
            chord("G", 0.0, 0.1),
            chord("D", 0.1, 0.2),
            chord("Em", 0.2, 0.3),
            chord("C", 0.3, 0.4),
        ]
        lyrics = {"words": [word("oi", 0.0, 0.4)]}
        chord_row, _ = _first_pair(cifra.render(analysis, lyrics))

        assert chord_row.split() == ["G", "D", "Em", "C"]
        assert "  " in chord_row or chord_row.count(" ") >= 3

    def test_a_long_silence_breaks_the_line(self, analysis):
        lyrics = {
            "words": [
                word("primeira", 0.0, 0.5),
                word("frase", 0.6, 1.0),
                word("segunda", 5.0, 5.5),  # four seconds later
                word("frase", 5.6, 6.0),
            ]
        }
        body = cifra.render(analysis, lyrics)
        assert "primeira frase" in body
        assert "segunda frase" in body
        assert "primeira frase segunda" not in body

    def test_a_gap_before_the_first_word_becomes_an_intro_block(self, analysis):
        lyrics = {"words": [word("tarde", 6.5, 7.0)]}
        text = cifra.render(analysis, lyrics)
        assert "[Intro]" in text
        # The chords played before anyone sings belong to the intro, not to the
        # line with the single word in it.
        intro = text.split("[Intro]")[1].splitlines()[1]
        assert "G" in intro and "D" in intro

    def test_solo_sections_are_labelled(self, analysis):
        analysis["lead"]["sections"] = [{"start": 0.0, "end": 5.0, "isSolo": True}]
        lyrics = {"words": [word("depois", 7.0, 7.4)]}
        assert "[Solo]" in cifra.render(analysis, lyrics)


class TestHeader:
    def test_key_is_named_in_portuguese(self, analysis):
        assert "Tom: G maior" in cifra.render(analysis)

    def test_transposition_reports_both_keys(self, analysis):
        text = cifra.render(analysis, transpose=2)
        assert "Tom: A maior" in text
        assert "original: G maior" in text
        assert "\nA " in "\n" + text or "A  " in text  # the chords moved too

    def test_capo_reports_the_shapes_being_fingered(self, analysis):
        text = cifra.render(analysis, capo=2)
        assert "Capotraste na 2ª casa" in text
        # G fingered with a capo on the second fret is an F shape.
        assert "Acordes:" in text
        assert " F " in text.split("Acordes:")[1].splitlines()[0] + " "

    def test_chord_summary_uses_brazilian_notation(self, analysis):
        analysis["chords"] = [chord("Gmaj7", 0.0, 2.0), chord("Bdim", 2.0, 4.0)]
        summary = cifra.render(analysis).split("Acordes:")[1].splitlines()[0]
        assert "G7M" in summary
        assert "B°" in summary


class TestWithoutLyrics:
    def test_falls_back_to_a_bar_grid(self, analysis):
        text = cifra.render(analysis)
        assert "[Instrumental]" in text
        grid = [line for line in text.splitlines() if line.startswith("|")]
        assert grid, text
        assert grid[0].count("|") == 5  # four bars per line

    def test_empty_analysis_does_not_crash(self):
        text = cifra.render({"chords": [], "beats": [], "key": {}})
        assert "sem acordes" in text


def _first_pair(text: str) -> tuple[str, str]:
    """The first chord row and the lyric row under it."""
    lines = text.splitlines()
    for index, line in enumerate(lines[:-1]):
        following = lines[index + 1]
        if line.strip() and following.strip() and not line.startswith(("Tom:", "Acordes:", "[")):
            if any(character.isalpha() for character in following) and not following.startswith("["):
                return line, following
    raise AssertionError(f"no chord/lyric pair found in:\n{text}")
