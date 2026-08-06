"""Tests for the stem bookkeeping around source separation.

The models themselves are not exercised here — they are hundreds of megabytes
and minutes of CPU each. What is tested is everything that decides *which* file
is which, which is where a mistake would be silent: a mixer that labels the
backing vocals as the lead looks like it works right up to the moment someone
mutes the wrong one on stage.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from app.analysis import stems


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(stems, "STEMS_DIR", tmp_path)
    return tmp_path


def write_stem(store, song_id: str, name: str, seconds: float = 0.5, level: float = 0.5) -> None:
    directory = store / song_id
    directory.mkdir(parents=True, exist_ok=True)
    samples = (level * np.sin(np.linspace(0, 440 * 2 * np.pi * seconds, int(22050 * seconds)))).astype(
        np.float32
    )
    sf.write(directory / f"{name}.{stems.STEM_FORMAT}", samples, 22050)


class TestOutputMatching:
    @pytest.mark.parametrize(
        ("keyword", "expected"),
        [("vocals", "song_(Vocals)_htdemucs.mp3"), ("drums", "song_(Drums)_htdemucs.mp3")],
    )
    def test_finds_the_output_by_the_name_the_model_gave_it(self, keyword, expected):
        outputs = [
            "/work/song_(Vocals)_htdemucs.mp3",
            "/work/song_(Drums)_htdemucs.mp3",
            "/work/song_(Bass)_htdemucs.mp3",
        ]
        found = stems._pick(outputs, keyword)
        assert found is not None and found.name == expected

    def test_matching_ignores_case(self):
        assert stems._pick(["/work/x_(VOCALS)_m.mp3"], "vocals") is not None

    def test_returns_none_when_the_stage_produced_nothing_matching(self):
        assert stems._pick(["/work/x_(Other)_m.mp3"], "vocals") is None

    def test_lead_and_backing_come_from_different_keywords(self):
        # This is the pairing the whole feature rests on: on a karaoke model the
        # "vocals" output is the lead and the "instrumental" output is what was
        # left of the vocal stem, which is the backing.
        split = ["/work/v_(Vocals)_kara.mp3", "/work/v_(Instrumental)_kara.mp3"]
        lead = stems._pick(split, "vocals")
        backing = stems._pick(split, "instrumental")
        assert lead is not None and backing is not None
        assert lead != backing


class TestStore:
    def test_unknown_stem_names_are_refused(self, store):
        write_stem(store, "abc", "lead")
        assert stems.stem_path("abc", "guitarra") is None

    def test_missing_files_report_as_missing(self, store):
        assert stems.stem_path("abc", "lead") is None

    def test_available_stems_keep_the_mixer_order(self, store):
        for name in ("other", "lead", "drums"):
            write_stem(store, "abc", name)
        assert [stem.name for stem in stems.available_stems("abc")] == ["lead", "drums", "other"]

    def test_available_stems_report_their_size(self, store):
        write_stem(store, "abc", "lead")
        assert stems.available_stems("abc")[0].bytes > 0

    def test_labels_are_in_portuguese(self, store):
        write_stem(store, "abc", "lead")
        assert stems.available_stems("abc")[0].to_dict()["label"] == "Voz principal"

    def test_deleting_removes_every_stem(self, store):
        write_stem(store, "abc", "lead")
        write_stem(store, "abc", "bass")
        stems.delete_stems("abc")
        assert stems.available_stems("abc") == []

    def test_deleting_a_song_without_stems_is_not_an_error(self, store):
        stems.delete_stems("never-separated")


class TestMixdown:
    def test_absent_stems_return_none_so_callers_can_fall_back(self, store):
        assert stems.load_stem_mono("abc", ["drums", "bass"], sr=22050) is None

    def test_present_stems_are_summed(self, store):
        write_stem(store, "abc", "drums")
        write_stem(store, "abc", "bass")
        mixed = stems.load_stem_mono("abc", ["drums", "bass"], sr=22050)
        assert mixed is not None and mixed.size > 0

    def test_a_missing_stem_does_not_sink_the_ones_that_exist(self, store):
        write_stem(store, "abc", "drums")
        assert stems.load_stem_mono("abc", ["drums", "bass"], sr=22050) is not None

    def test_stems_of_different_lengths_do_not_crash_the_sum(self, store):
        write_stem(store, "abc", "drums", seconds=0.5)
        write_stem(store, "abc", "bass", seconds=0.3)
        mixed = stems.load_stem_mono("abc", ["drums", "bass"], sr=22050)
        assert mixed is not None


class TestPartialSplit:
    """What happens when the karaoke stage cannot find one of the two halves.

    The separator skips writing a stem it judges near-silent, so a missing
    output is an answer rather than a fault — an instrumental has no lead vocal
    to find. Failing the whole separation over that would discard four good
    stems to punish a song for its arrangement.
    """

    def test_a_missing_half_is_an_answer_not_an_error(self):
        # Only the "instrumental" half came back: the model heard no lead.
        split = ["/work/v_(Instrumental)_kara.mp3"]
        assert stems._pick(split, "lead") is None
        assert stems._pick(split, "vocals") is None
        assert stems._pick(split, "instrumental") is not None

    def test_both_halves_are_recognised_when_both_exist(self):
        split = ["/work/v_(Vocals)_kara.mp3", "/work/v_(Instrumental)_kara.mp3"]
        assert stems._pick(split, "vocals") is not None
        assert stems._pick(split, "instrumental") is not None
