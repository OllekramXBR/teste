"""Tests for transposed and time-stretched renders.

The rendering itself is a phase vocoder and is not exercised here — it is
librosa's, and running it on real audio would make the suite take minutes. What
is tested is everything around it: the naming that keeps two variants apart, the
range checks that stop a stray request costing twenty minutes of CPU, and the
listing the player reads.
"""

from __future__ import annotations

import pytest

from app.analysis import variants


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(variants, "STEMS_DIR", tmp_path)
    return tmp_path


class TestNaming:
    def test_a_key_encodes_both_the_pitch_and_the_speed(self):
        assert variants.variant_key(2, 1.0) == "tp2_r100"
        assert variants.variant_key(-3, 0.75) == "tm3_r75"

    def test_different_combinations_never_collide(self):
        keys = {
            variants.variant_key(semitones, rate)
            for semitones in range(-3, 4)
            for rate in (0.75, 1.0, 1.25)
        }
        assert len(keys) == 7 * 3

    def test_the_key_survives_a_url_without_escaping(self):
        # It becomes a path segment, so a sign written as '+' or '-' would be
        # either escaped or, worse, silently rewritten by something in between.
        for semitones in (-7, 0, 7):
            key = variants.variant_key(semitones, 1.0)
            assert key.isascii() and "/" not in key and "+" not in key


class TestRange:
    @pytest.mark.parametrize("semitones", [8, -8, 12])
    def test_transposition_beyond_the_useful_range_is_refused(self, store, semitones):
        with pytest.raises(ValueError):
            variants.render("abc", semitones, 1.0)

    @pytest.mark.parametrize("rate", [0.4, 1.6, 2.0])
    def test_speeds_beyond_the_useful_range_are_refused(self, store, rate):
        with pytest.raises(ValueError):
            variants.render("abc", 0, rate)

    def test_asking_for_the_original_is_refused_rather_than_rendered(self, store):
        # Twenty minutes of CPU to reproduce a file that already exists.
        with pytest.raises(ValueError):
            variants.render("abc", 0, 1.0)


class TestListing:
    def test_a_song_with_no_variants_lists_none(self, store):
        assert variants.available("abc") == []

    def test_a_rendered_variant_is_listed_with_its_stems(self, store):
        directory = store / "abc" / "variants" / "tp2_r100"
        directory.mkdir(parents=True)
        (directory / f"lead.{variants.STEM_FORMAT}").write_bytes(b"x")
        (directory / f"backing.{variants.STEM_FORMAT}").write_bytes(b"x")

        listed = variants.available("abc")
        assert listed == [{"key": "tp2_r100", "stems": ["backing", "lead"]}]

    def test_an_empty_directory_is_not_offered_as_a_variant(self, store):
        # A render that died halfway must not look playable.
        (store / "abc" / "variants" / "tp2_r100").mkdir(parents=True)
        assert variants.available("abc") == []
