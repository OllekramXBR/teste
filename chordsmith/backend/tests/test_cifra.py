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
        analysis["chords"] = [
            chord("G", 0.0, 1.0),
            chord("D", 1.0, 4.0),
            chord("Em", 4.0, 8.0),
            chord("C", 8.0, 12.0),
        ]
        analysis["lead"]["sections"] = [{"start": 4.0, "end": 12.0, "isSolo": True}]
        lyrics = {"words": [word("antes", 0.0, 0.4), word("depois", 12.5, 12.9)]}
        assert "[Solo]" in cifra.render(analysis, lyrics)

    def test_the_intro_is_never_relabelled_as_a_solo(self, analysis):
        # An intro is very often a lead line, so the solo detector fires on it.
        # Calling the opening of the song a solo tells the player something
        # false about the form.
        analysis["lead"]["sections"] = [{"start": 0.0, "end": 6.0, "isSolo": True}]
        lyrics = {"words": [word("tarde", 6.5, 7.0)]}
        text = cifra.render(analysis, lyrics)
        assert "[Intro]" in text
        assert "[Solo]" not in text

    def test_a_new_transcribed_phrase_starts_a_new_line(self, analysis):
        # The two phrases are only 0.3s apart — under PHRASE_GAP — so only the
        # recogniser's own segmentation can tell them apart. Without it the
        # first word of the second phrase gets dragged onto the first line.
        lyrics = {
            "segments": [
                {"start": 0.0, "end": 0.9, "text": "primeira frase"},
                {"start": 1.2, "end": 2.1, "text": "segunda frase"},
            ],
            "words": [
                word("primeira", 0.0, 0.5),
                word("frase", 0.5, 0.9),
                word("segunda", 1.2, 1.7),
                word("frase", 1.7, 2.1),
            ],
        }
        rendered = cifra.render(analysis, lyrics)
        assert "primeira frase" in rendered
        assert "segunda frase" in rendered
        assert "frase segunda" not in rendered


class TestSimplify:
    @pytest.mark.parametrize(
        ("decoded", "simplified"),
        [("C6", "C"), ("Csus2", "C"), ("Csus4", "C"), ("Cmaj7", "C"), ("Am7", "Am"), ("Am6", "Am")],
    )
    def test_extensions_collapse_to_the_triad(self, analysis, decoded, simplified):
        analysis["chords"] = [chord(decoded, 0.0, 4.0)]
        summary = cifra.render(analysis).split("Acordes:")[1].splitlines()[0].split()
        assert summary == [simplified]

    def test_diminished_and_augmented_survive(self, analysis):
        analysis["chords"] = [chord("Bdim", 0.0, 2.0), chord("Caug", 2.0, 4.0)]
        summary = cifra.render(analysis).split("Acordes:")[1].splitlines()[0]
        assert "B°" in summary and "C+" in summary

    def test_a_chord_shorter_than_one_beat_is_dropped(self, analysis):
        # 129 BPM puts a beat at 0.465s; the D# lasts a fifth of that.
        analysis["bpm"] = 129.0
        analysis["chords"] = [
            chord("G", 0.0, 2.0),
            chord("D#", 2.0, 2.1),
            chord("G", 2.1, 4.0),
        ]
        summary = cifra.render(analysis).split("Acordes:")[1].splitlines()[0].split()
        assert summary == ["G"]

    def test_neighbours_merge_once_they_look_the_same(self, analysis):
        analysis["chords"] = [
            chord("C", 0.0, 2.0),
            chord("C6", 2.0, 4.0),
            chord("Cmaj7", 4.0, 6.0),
        ]
        lyrics = {"words": [word("uma", 0.0, 0.4), word("linha", 0.5, 0.9)]}
        chord_row, _ = _first_pair(cifra.render(analysis, lyrics))
        assert chord_row.split() == ["C"]

    def test_turning_simplification_off_shows_what_the_decoder_said(self, analysis):
        analysis["chords"] = [chord("Cmaj7", 0.0, 4.0)]
        assert "C7M" in cifra.render(analysis, simplify=False)
        assert "C7M" not in cifra.render(analysis, simplify=True)


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
        # Simplification off: this is about how a seventh is spelled, and with
        # it on the seventh is gone before the speller ever sees it.
        analysis["chords"] = [chord("Gmaj7", 0.0, 2.0), chord("Bdim", 2.0, 4.0)]
        summary = cifra.render(analysis, simplify=False).split("Acordes:")[1].splitlines()[0]
        assert "G7M" in summary
        assert "B°" in summary


class TestChordPro:
    def test_the_header_carries_title_key_and_capo(self, analysis):
        text = cifra.render_chordpro(analysis, title="Uma", artist="Outro", capo=2)
        assert "{title: Uma}" in text
        assert "{artist: Outro}" in text
        assert "{key: G}" in text
        assert "{capo: 2}" in text

    def test_chords_sit_inline_before_the_word_they_land_on(self, analysis):
        analysis["chords"] = [chord("G", 0.0, 0.5), chord("D", 0.5, 1.0)]
        lyrics = {"words": [word("um", 0.0, 0.4), word("dois", 0.5, 0.9)]}
        line = [
            row for row in cifra.render_chordpro(analysis, lyrics).splitlines() if "[G]" in row
        ][0]
        assert line.startswith("[G]um")
        assert "[D]dois" in line

    def test_notation_is_brazilian_here_too(self, analysis):
        analysis["chords"] = [chord("Gmaj7", 0.0, 4.0)]
        lyrics = {"words": [word("nota", 0.0, 0.5)]}
        assert "[G7M]" in cifra.render_chordpro(analysis, lyrics, simplify=False)

    def test_sections_become_comments(self, analysis):
        lyrics = {"words": [word("tarde", 6.5, 7.0)]}
        assert "{comment: Intro}" in cifra.render_chordpro(analysis, lyrics)

    def test_without_lyrics_it_still_produces_the_grid(self, analysis):
        text = cifra.render_chordpro(analysis)
        assert "{comment: Instrumental}" in text
        assert any(row.startswith("|") for row in text.splitlines())


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
