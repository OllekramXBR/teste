"""Tests for the Cifra Club search/fetch/compare module.

Nothing here talks to the network: the page fetch and the search payload are
replaced with fixed bodies, so the parsing, the flight decoding, the storage
round-trip and the comparison verdicts are what get exercised.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app import cifraclub, storage


class FakeResponse:
    """A minimal urllib response: context manager, read() up to a size."""

    headers = SimpleNamespace(get_content_charset=lambda: "utf-8")

    def __init__(self, body: bytes):
        self.body = body
        self.pos = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body)
        chunk = self.body[self.pos : self.pos + size]
        self.pos += len(chunk)
        return chunk


def test_fetch_falls_back_to_latin1(monkeypatch):
    # The site declares utf-8 but sends latin-1 bytes; strict utf-8 decoding
    # fails on the first accent and the fetch must retry as latin-1.
    body = "Legião Urbana: não há coração aqui".encode("latin-1")

    def fake_urlopen(request, timeout):
        return FakeResponse(body)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    assert "Legião Urbana: não há coração aqui" in cifraclub._fetch("https://example.com/")


def test_search_filters_and_dedupes(monkeypatch):
    payload = json.dumps(
        {
            "response": {
                "docs": [
                    {"id_song": 1, "txt": "A", "art": "B", "dns": "a", "url": "a", "tipo": "2"},
                    {"id_song": 1, "txt": "A dup", "art": "B", "dns": "a", "url": "a", "tipo": "2"},
                    {"id_song": 2, "txt": "C", "art": "D", "dns": "c", "url": "c", "tipo": "1"},
                    {"id_song": 3, "txt": "E", "art": "F", "dns": "e", "url": "e", "tipo": "3"},
                    {"id_song": 4, "txt": "G", "art": "H", "dns": "g", "url": "g", "tipo": "2"},
                ]
            }
        }
    )
    monkeypatch.setattr(cifraclub, "_fetch", lambda url: payload)
    results = cifraclub.search("abc", limit=3)
    assert [r.id for r in results] == [1, 3, 4]


def _flight_page(rows: str) -> str:
    """Wrap flight rows in the push segments ``_decode_flight`` expects."""
    escaped = json.dumps(rows)[1:-1]
    return f'self.__next_f.push([1,"{escaped}"])'


CHART_TEXT = (
    "[Intro] <b>C7M</b>  <b>Am7</b>\n"
    "Água é a vida\n"
    "#t1#  <b>D5</b>\n#t2#E|---2---#/t2##/t1#"
)


def _chart_flight() -> str:
    song_row = json.dumps(
        [3, ["$", "div", None, {"songData": {"id": 42, "title": "Teste", "content": "$7"}}]]
    )
    hex_len = format(len(CHART_TEXT.encode("utf-8")), "x")
    return f"\n6:I{song_row}\n7:T{hex_len},{CHART_TEXT}\n8:J[null]"


def test_parse_flight_reads_byte_lengths():
    # The T row length is in bytes; the text carries accents and a real
    # newline, so byte length and character count diverge. A wrong slice
    # swallows the row that follows — the regression this test exists for.
    rows = cifraclub._parse_flight(_chart_flight())
    assert "6" in rows and "7" in rows and "8" in rows
    assert rows["7"] == "T" + CHART_TEXT
    assert rows["8"] == "J[null]"


def test_parse_chart_end_to_end():
    chart = cifraclub.parse_chart(_flight_page(_chart_flight()))
    assert chart["source"]["id"] == 42
    assert chart["source"]["title"] == "Teste"
    assert chart["chords"] == ["C7M", "Am7"]
    kinds = [line["kind"] for line in chart["lines"]]
    assert kinds == ["verse", "verse", "tab"]
    tab = chart["lines"][2]
    assert "D5" in tab["text"] and "E|---2---" in tab["text"]


def test_parse_pre_text_keeps_chord_columns():
    lines = cifraclub._parse_pre_text("[Intro] <b>C7M</b>  <b>Am7</b>\n")
    assert lines[0]["text"] == "[Intro] C7M  Am7"
    assert lines[0]["chords"] == [{"name": "C7M", "col": 8}, {"name": "Am7", "col": 13}]


def test_chart_lyric_lines_strips_chords_and_sections():
    chart = cifraclub.parse_chart(_flight_page(_chart_flight()))
    # The intro line is nothing but chords and a section tag, so it vanishes;
    # the tab line is skipped entirely; only the sung words survive.
    assert cifraclub.chart_lyric_lines(chart) == ["Água é a vida"]


def test_chart_lyric_lines_keeps_words_around_inline_chords():
    lines = [
        {"kind": "verse", "text": "Cifra G com palavras", "chords": [{"name": "G", "col": 6}]},
        {"kind": "verse", "text": "[Refrão] C e mais", "chords": [{"name": "C", "col": 9}]},
        {"kind": "verse", "text": "Sem acorde", "chords": []},
        {"kind": "tab", "text": "E|---3---", "chords": [{"name": "D5", "col": 3}]},
    ]
    assert cifraclub.chart_lyric_lines({"lines": lines}) == [
        "Cifra com palavras",
        "e mais",
        "Sem acorde",
    ]


def _previous_lyrics() -> dict:
    return {
        "language": "pt",
        "languageProbability": 0.9,
        "model": "base",
        "audioSeconds": 4.8,
        "segments": [
            {"start": 0.0, "end": 2.4, "text": "ouço a água"},
            {"start": 2.4, "end": 4.8, "text": "vida que passa"},
        ],
        "words": [
            {"text": "ouço", "start": 0.0, "end": 1.2, "probability": 0.8},
            {"text": "a", "start": 1.2, "end": 1.8, "probability": 0.8},
            {"text": "água", "start": 1.8, "end": 2.4, "probability": 0.8},
            {"text": "vida", "start": 2.4, "end": 3.6, "probability": 0.8},
            {"text": "que", "start": 3.6, "end": 4.2, "probability": 0.8},
            {"text": "passa", "start": 4.2, "end": 4.8, "probability": 0.8},
        ],
        "wordCount": 6,
        "source": "mix",
    }


def test_correct_lyrics_line_for_line_keeps_timing():
    chart = {
        "lines": [
            {"kind": "verse", "text": "Água é a vida", "chords": []},
            {"kind": "verse", "text": "Corre pro mar", "chords": []},
        ]
    }
    corrected = cifraclub.correct_lyrics(chart, _previous_lyrics())
    assert corrected is not None
    # One segment per chart line, so each line keeps the segment's own timing.
    assert corrected["segments"] == [
        {"start": 0.0, "end": 2.4, "text": "Água é a vida"},
        {"start": 2.4, "end": 4.8, "text": "Corre pro mar"},
    ]
    assert [word["text"] for word in corrected["words"]] == [
        "Água", "é", "a", "vida", "Corre", "pro", "mar",
    ]
    assert corrected["wordCount"] == 7
    assert corrected["edited"] is True
    assert corrected["correctedByChart"] is True
    # Everything that describes the source survives the rebuild.
    assert corrected["model"] == "base"
    assert corrected["source"] == "mix"


def test_correct_lyrics_lays_uneven_counts_across_the_sung_span():
    chart = {
        "lines": [
            {"kind": "verse", "text": "Água é a vida", "chords": []},
            {"kind": "verse", "text": "Corre pro mar", "chords": []},
            {"kind": "verse", "text": "Sobe", "chords": []},
        ]
    }
    corrected = cifraclub.correct_lyrics(chart, _previous_lyrics())
    assert corrected is not None
    segments = corrected["segments"]
    assert [segment["text"] for segment in segments] == ["Água é a vida", "Corre pro mar", "Sobe"]
    assert segments[0]["start"] == 0.0
    assert segments[-1]["end"] == 4.8
    assert [segment["start"] for segment in segments[1:]] == [
        segments[0]["end"],
        segments[1]["end"],
    ]
    assert corrected["wordCount"] == 8
    assert corrected["edited"] is True
    assert corrected["correctedByChart"] is True


def test_correct_lyrics_returns_none_without_anchor():
    chart = {"lines": [{"kind": "verse", "text": "Sem timing", "chords": []}]}
    # No transcription yet: there is nothing to give the correction a skeleton.
    assert cifraclub.correct_lyrics(chart, None) is None
    assert cifraclub.correct_lyrics(chart, {"segments": []}) is None
    # A chart with nothing to sing (only chords and tabs) also yields nothing.
    chord_only = {
        "lines": [
            {
                "kind": "verse",
                "text": "G   D",
                "chords": [{"name": "G", "col": 0}, {"name": "D", "col": 4}],
            }
        ]
    }
    assert cifraclub.correct_lyrics(chord_only, _previous_lyrics()) is None


def test_normalize_label():
    cases = {
        "C7M": ("C", "maj7"),
        "Am7": ("A", "m7"),
        "Bm7(b5)": ("B", "m7b5"),
        "C°": ("C", "dim"),
        "C°7": ("C", "dim7"),
        "E5": ("E", ""),
        "C+": ("C", "aug"),
        "G7/9": ("G", "7"),
        "Bb": ("Bb", ""),
        "F#m": ("F#", "m"),
        "Asus": ("A", "sus4"),
    }
    from app.analysis import theory

    for raw, (root_name, quality) in cases.items():
        norm = cifraclub.normalize_label(raw)
        assert norm is not None, raw
        # A pitch class has two spellings (Bb is A#); either is correct.
        spellings = {theory.SHARP_NAMES[norm["root"]], theory.FLAT_NAMES[norm["root"]]}
        assert root_name in spellings, raw
        assert norm["quality"] == quality, raw

    assert cifraclub.normalize_label("[Intro]") is None
    assert cifraclub.normalize_label("H") is None


def _progression_analysis() -> dict:
    chords = [
        {"label": "G", "start": 0.0, "end": 2.4, "startBeat": 0, "endBeat": 3},
        {"label": "D", "start": 2.4, "end": 4.8, "startBeat": 4, "endBeat": 7},
        {"label": "Em", "start": 4.8, "end": 7.2, "startBeat": 8, "endBeat": 11},
        {"label": "C", "start": 7.2, "end": 9.6, "startBeat": 12, "endBeat": 15},
    ]
    beats = []
    for bar in range(1, 5):
        for beat_in_bar in range(4):
            label = chords[(bar - 1)]["label"]
            beats.append(
                {
                    "index": (bar - 1) * 4 + beat_in_bar,
                    "time": (bar - 1) * 2.4 + beat_in_bar * 0.6,
                    "bar": bar,
                    "beatInBar": beat_in_bar + 1,
                    "label": label,
                }
            )
    return {"useFlats": False, "chords": chords, "beats": beats}


def test_compare_verdicts():
    analysis = _progression_analysis()

    matched = cifraclub.compare(analysis, ["G", "D", "Em", "C"])
    assert [v["verdict"] for v in matched["verdicts"]] == ["match"] * 4
    assert matched["stats"]["match"] == 4

    # The letters are compared, not the reduced chords: G7M is not a plain G,
    # so it is "próximo" (same root, different letter) rather than "casa".
    collapsed = cifraclub.compare(analysis, ["G7M", "D", "Em", "C"])
    assert collapsed["verdicts"][0]["verdict"] == "partial"
    assert collapsed["verdicts"][0]["web"] == "G7M"

    # Same root, different chord quality: partial.
    partial = cifraclub.compare(analysis, ["Gm", "D", "Em", "C"])
    assert partial["verdicts"][0]["verdict"] == "partial"

    # Different root: diff.
    wrong = cifraclub.compare(analysis, ["A", "D", "Em", "C"])
    assert wrong["verdicts"][0]["verdict"] == "diff"

    # A chart that never mentions the last two chords leaves them missing.
    short = cifraclub.compare(analysis, ["G", "D"])
    assert [v["verdict"] for v in short["verdicts"]] == ["match", "match", "missing", "missing"]

    # An unreadable label is counted, never crashed on.
    unreadable = cifraclub.compare(analysis, ["G", "ZZ9", "Em", "C"])
    assert unreadable["stats"]["unknown"] == 1
    assert unreadable["verdicts"][0]["verdict"] == "match"


def test_compare_per_bar():
    analysis = _progression_analysis()
    result = cifraclub.compare(analysis, ["G", "D", "Em", "C"])
    assert [bar["bar"] for bar in result["perBar"]] == [1, 2, 3, 4]
    assert all(bar["verdict"] == "match" for bar in result["perBar"])


def test_parse_key():
    assert cifraclub._parse_key("G") == (7, "major")
    assert cifraclub._parse_key("Em") == (4, "minor")
    assert cifraclub._parse_key("Bbm") == (10, "minor")
    assert cifraclub._parse_key("F#") == (6, "major")
    assert cifraclub._parse_key("") is None
    assert cifraclub._parse_key("ZZ9") is None
    assert cifraclub._parse_key(None) is None


def test_correct_replaces_letters_and_key():
    analysis = _progression_analysis()
    corrected = cifraclub.correct(analysis, ["G7M", "D", "Em", "C"], "G")

    # The chart's tom wins, marked as authoritative.
    assert corrected["key"]["tonic"] == 7
    assert corrected["key"]["mode"] == "major"
    assert corrected["key"]["name"] == "G major"
    assert corrected["key"]["confidence"] == 1.0
    assert corrected["useFlats"] is False

    # The first detected span took the chart's chord, letters and quality.
    assert corrected["chords"][0]["root"] == 7
    assert corrected["chords"][0]["quality"] == "maj7"
    assert corrected["chords"][0]["label"] == "Gmaj7"
    assert corrected["chords"][0]["notes"] == [7, 11, 2, 6]

    # Timing survives the rewrite.
    assert corrected["chords"][0]["start"] == 0.0
    assert corrected["chords"][0]["end"] == 2.4

    # Every beat inside the corrected span carries the corrected letter.
    assert all(beat["label"] == "Gmaj7" for beat in corrected["beats"][:4])
    assert corrected["beats"][0]["root"] == 7
    assert corrected["uniqueChords"] == ["C", "D", "Em", "Gmaj7"]


def test_correct_uses_chart_as_truth_when_roots_differ():
    analysis = _progression_analysis()
    corrected = cifraclub.correct(analysis, ["A", "B", "C#m", "F"], "A")
    assert corrected["key"]["name"] == "A major"
    assert [chord["label"] for chord in corrected["chords"]] == ["A", "B", "C#m", "F"]
    assert corrected["beats"][0]["label"] == "A"


def test_correct_keeps_detected_key_when_chart_has_none():
    analysis = _progression_analysis()
    analysis["key"] = {"tonic": 2, "mode": "minor", "name": "D minor", "confidence": 0.42}
    corrected = cifraclub.correct(analysis, ["G", "D", "Em", "C"], "")
    assert corrected["key"]["tonic"] == 2
    assert corrected["key"]["mode"] == "minor"
    assert corrected["key"]["confidence"] == 0.42
    # The chord letters still follow the chart when it offers no tom.
    assert corrected["chords"][0]["label"] == "G"


def test_correct_does_not_touch_unmatched_spans():
    analysis = _progression_analysis()
    # A chart that never mentions the last two chords leaves them as heard.
    corrected = cifraclub.correct(analysis, ["G", "D"], "G")
    assert corrected["chords"][0]["label"] == "G"
    assert corrected["chords"][1]["label"] == "D"
    assert corrected["chords"][2]["label"] == "Em"
    assert corrected["chords"][3]["label"] == "C"


def test_storage_cifra_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATABASE_PATH", tmp_path / "test.db")
    storage.init_db()
    storage.create_song("s1", "T", "A", "t.mp3", "t.mp3", "audio/mpeg", 1)

    saved = storage.save_cifra(
        "s1", source_id=7, title="T", artist="A", key="Em",
        chords=["C", "G"], lines=[{"kind": "verse", "text": "x", "chords": []}],
    )
    assert saved["sourceId"] == 7
    assert saved["chords"] == ["C", "G"]

    # Re-importing replaces rather than stacking.
    storage.save_cifra("s1", source_id=8, title="T2", chords=["D"])
    again = storage.get_cifra("s1")
    assert again["sourceId"] == 8
    assert again["chords"] == ["D"]

    assert storage.delete_cifra("s1") is True
    assert storage.get_cifra("s1") is None
