"""Tests for the mp3.pm search-and-download fallback.

Nothing here talks to the network: the fetch is replaced with a fixed page or a
raised status, and the download with a fake response, so the parsing and the
route behaviour are what is exercised, not mp3.pm's availability.
"""

from __future__ import annotations

import urllib.error
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import mp3pm
from app.routes import mp3pm as mp3pm_routes

SAMPLE_PAGE = """
<h2 class="mtitle">what do you mean</h2><ul class="mp3list">
<li class="cplayer-sound-item" data-sound-id="44032646"
  data-sound-url="https://cs1.mp3.pm/listen/44032646/abc.mp3"
  data-download-url="https://cs1.mp3.pm/download/44032646/abc.mp3">
  <div class="mp3list-btns">
    <a href="javascript:void(0);" class="mp3list-btn-play cplayer-ui-play" title="play">(play)</a>
    <a href="https://zds.mp3.pm/song/44032646-what-do-you-mean/" class="mp3list-btn-download cplayer-ui-download" title="download">(download)</a>
  </div>
  <h4>
    <a href="https://zds.mp3.pm/"><i class="cplayer-data-sound-author">ZDS</i></a>
    <a href="https://zds.mp3.pm/song/44032646-what-do-you-mean/"><b class="cplayer-data-sound-title">What Do You Mean?</b></a>
  </h4>
  <em class="cplayer-data-sound-time">06:47</em>
</li>
<li class="cplayer-sound-item" data-sound-id="44980019"
  data-download-url="https://cs1.mp3.pm/download/44980019/def.mp3">
  <h4>
    <a href="https://zds.mp3.pm/"><i class="cplayer-data-sound-author">ZDS</i></a>
    <a href="https://zds.mp3.pm/song/44980019/"><b class="cplayer-data-sound-title">What Do You Mean?</b></a>
  </h4>
  <em class="cplayer-data-sound-time">1:02:03</em>
</li>
</ul>
"""


class FakeResponse:
    """A minimal urllib response: context manager, read() up to a size."""

    headers = SimpleNamespace(
        get_content_charset=lambda: None,
        get_content_type=lambda: "audio/mpeg",
    )

    def __init__(self, body: bytes):
        self.body = body
        self.pos = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1):
        if self.pos >= len(self.body):
            return b""
        end = len(self.body) if size < 0 else min(self.pos + size, len(self.body))
        chunk = self.body[self.pos : end]
        self.pos = end
        return chunk


@pytest.fixture(autouse=True)
def no_page_delay(monkeypatch):
    """A search can span pages; the politeness pause is irrelevant in tests."""
    monkeypatch.setattr(mp3pm.time, "sleep", lambda _seconds: None)


def page_fetch(*responses):
    """A ``_fetch`` stand-in serving one response per page URL.

    Page one is the bare subdomain; later pages carry a ``/page/N/`` path, so
    each URL is matched to the response at its index. Any remaining page is
    treated as 404, which is how the real site signals "no more results".
    """
    calls: list[str] = []

    def _fetch(url: str) -> str:
        calls.append(url)
        page_numbers = [candidate for candidate in url.split("/") if candidate.isdigit()]
        number = int(page_numbers[-1]) if page_numbers else 1
        if number - 1 < len(responses):
            return responses[number - 1]
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    _fetch.calls = calls  # type: ignore[attr-defined]
    return _fetch


class TestParsing:
    def test_results_are_extracted(self, monkeypatch):
        monkeypatch.setattr(mp3pm, "_fetch", page_fetch(SAMPLE_PAGE))
        tracks = mp3pm.search("what do you mean")
        assert len(tracks) == 2

        first = tracks[0]
        assert first.sound_id == "44032646"
        assert first.artist == "ZDS"
        assert first.title == "What Do You Mean?"
        assert first.duration == 6 * 60 + 47
        assert first.download_url.startswith("https://cs1.mp3.pm/download/")
        assert first.listen_url == "https://cs1.mp3.pm/listen/44032646/abc.mp3"

    def test_hours_are_accounted_for(self):
        assert mp3pm._parse_duration("1:02:03") == 3723

    def test_limit_is_respected(self, monkeypatch):
        monkeypatch.setattr(mp3pm, "_fetch", page_fetch(SAMPLE_PAGE))
        assert len(mp3pm.search("what do you mean", limit=1)) == 1

    def test_no_results_answers_404_with_an_empty_list(self, monkeypatch):
        def refuse(url: str):
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

        monkeypatch.setattr(mp3pm, "_fetch", refuse)
        assert mp3pm.search("nothing exists like this") == []

    def test_other_statuses_are_errors(self, monkeypatch):
        def refuse(url: str):
            raise urllib.error.HTTPError(url, 503, "Service Unavailable", None, None)

        monkeypatch.setattr(mp3pm, "_fetch", refuse)
        with pytest.raises(mp3pm.Mp3pmError):
            mp3pm.search("anything")

    def test_network_failure_is_an_error(self, monkeypatch):
        def refuse(url: str):
            raise mp3pm.Mp3pmError("mp3.pm is unreachable: no route to host")

        monkeypatch.setattr(mp3pm, "_fetch", refuse)
        with pytest.raises(mp3pm.Mp3pmError):
            mp3pm.search("anything")

    def test_empty_or_unusable_queries_return_nothing(self):
        assert mp3pm.search("") == []
        assert mp3pm.search("   ---   ") == []

    def test_find_locates_by_id(self, monkeypatch):
        monkeypatch.setattr(mp3pm, "_fetch", page_fetch(SAMPLE_PAGE))
        found = mp3pm.find("what do you mean", "44980019")
        assert found is not None
        assert found.duration == 3723
        assert mp3pm.find("what do you mean", "00000000") is None


class TestPagination:
    def test_second_page_is_fetched(self, monkeypatch):
        fetch = page_fetch(SAMPLE_PAGE, SAMPLE_PAGE)
        monkeypatch.setattr(mp3pm, "_fetch", fetch)
        tracks = mp3pm.search("what do you mean")
        # Both pages carried the same two recordings, so dedupe collapses the
        # repeats instead of showing the top of page one twice.
        assert len(tracks) == 2
        assert sorted(track.sound_id for track in tracks) == ["44032646", "44980019"]
        assert any(url.endswith("/page/2/") for url in fetch.calls)

    def test_distinct_recordings_from_both_pages_are_kept(self, monkeypatch):
        later = SAMPLE_PAGE.replace('data-sound-id="44980019"', 'data-sound-id="77777777"')
        monkeypatch.setattr(mp3pm, "_fetch", page_fetch(SAMPLE_PAGE, later))
        tracks = mp3pm.search("what do you mean")
        assert sorted(track.sound_id for track in tracks) == ["44032646", "44980019", "77777777"]

    def test_second_page_404_ends_the_search(self, monkeypatch):
        monkeypatch.setattr(mp3pm, "_fetch", page_fetch(SAMPLE_PAGE))
        assert len(mp3pm.search("what do you mean")) == 2

    def test_page_cap_is_honoured(self, monkeypatch):
        fetch = page_fetch(SAMPLE_PAGE)
        monkeypatch.setattr(mp3pm, "_fetch", fetch)
        mp3pm.search("what do you mean", pages=3)
        assert not any(url.endswith("/page/3/") for url in fetch.calls)


class TestSlug:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("What Do You Mean?", "what-do-you-mean"),
            ("Legião Urbana", "legiao-urbana"),
            ("   spaced   out  ", "spaced-out"),
        ],
    )
    def test_queries_become_subdomains(self, query, expected):
        assert mp3pm._slug(query) == expected


class TestDownload:
    def test_streams_into_the_music_folder(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda request, timeout: FakeResponse(b"ID3\x00\x00fake-mp3-bytes"),
        )
        track = mp3pm.Track(
            sound_id="44032646",
            title="What Do You Mean?",
            artist="ZDS",
            duration=407,
            download_url="https://cs1.mp3.pm/download/44032646/abc.mp3",
        )

        saved = mp3pm.download(track, destination=tmp_path)
        assert saved == tmp_path / "ZDS - What Do You Mean.mp3"
        assert saved.read_bytes() == b"ID3\x00\x00fake-mp3-bytes"

    def test_accepts_a_raw_mpeg_frame_without_an_id3_tag(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda request, timeout: FakeResponse(b"\xff\xfb\x90\x00bytes"),
        )
        track = mp3pm.Track("1", "Song", "Artist", 0, "https://cs1.mp3.pm/d/1/x.mp3")
        saved = mp3pm.download(track, destination=tmp_path)
        assert saved.read_bytes() == b"\xff\xfb\x90\x00bytes"

    def test_refuses_html_that_is_not_audio(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "urllib.request.urlopen",
            lambda request, timeout: FakeResponse(b"<html><body>404 not found</body></html>"),
        )
        track = mp3pm.Track("1", "Song", "Artist", 0, "https://cs1.mp3.pm/d/1/x.mp3")
        with pytest.raises(mp3pm.Mp3pmError):
            mp3pm.download(track, destination=tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_removes_a_partial_file_on_failure(self, tmp_path, monkeypatch):
        def explode(request, timeout):
            raise urllib.error.URLError("connection reset")

        monkeypatch.setattr("urllib.request.urlopen", explode)
        track = mp3pm.Track("1", "Song", "Artist", 0, "https://cs1.mp3.pm/d/1/x.mp3")
        with pytest.raises(mp3pm.Mp3pmError):
            mp3pm.download(track, destination=tmp_path)
        assert list(tmp_path.iterdir()) == []


@pytest.fixture
def router_client(monkeypatch, tmp_path):
    """A bare app with only the mp3pm routes, real storage replaced by fakes."""
    audio_dir = tmp_path / "audio"
    music_dir = tmp_path / "music"
    monkeypatch.setattr(mp3pm_routes, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(mp3pm_routes, "MUSIC_DIR", music_dir)

    app = FastAPI()
    app.include_router(mp3pm_routes.router)
    return TestClient(app)


def test_search_route_returns_results(router_client, monkeypatch):
    track = mp3pm.Track(
        "44032646", "What Do You Mean?", "ZDS", 407, "https://cs1.mp3.pm/d/44032646/a.mp3"
    )
    monkeypatch.setattr(mp3pm_routes.mp3pm, "search", lambda query, limit=20: [track])

    body = router_client.get("/api/mp3pm/search", params={"q": "what do you mean"}).json()
    assert body["results"] == [
        {
            "soundId": "44032646",
            "title": "What Do You Mean?",
            "artist": "ZDS",
            "duration": 407,
            "downloadUrl": "https://cs1.mp3.pm/d/44032646/a.mp3",
            "listenUrl": "",
        }
    ]


def test_search_route_reports_upstream_failure(router_client, monkeypatch):
    def boom(query, limit=20):
        raise mp3pm.Mp3pmError("mp3.pm is unreachable: nope")

    monkeypatch.setattr(mp3pm_routes.mp3pm, "search", boom)
    response = router_client.get("/api/mp3pm/search", params={"q": "x"})
    assert response.status_code == 502


def test_import_route_downloads_and_imports(router_client, monkeypatch, tmp_path):
    track = mp3pm.Track("44032646", "What Do You Mean?", "ZDS", 407, "https://x/a.mp3")
    monkeypatch.setattr(mp3pm_routes.mp3pm, "find", lambda query, sound_id: track)

    def fake_download(the_track, destination=None):
        target = (destination or mp3pm_routes.MUSIC_DIR) / "ZDS - What Do You Mean.mp3"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"ID3fake")
        return target

    monkeypatch.setattr(mp3pm_routes.mp3pm, "download", fake_download)

    created = {"id": "abc123", "title": "What Do You Mean?", "status": "pending"}
    calls: dict = {}

    def fake_create_song(**kwargs):
        calls.update(kwargs)
        return {**created, **{k: v for k, v in kwargs.items() if k in ("title", "artist")}}

    monkeypatch.setattr(mp3pm_routes.storage, "new_id", lambda: "abc123")
    monkeypatch.setattr(mp3pm_routes.storage, "create_song", fake_create_song)
    monkeypatch.setattr(mp3pm_routes.jobs, "enqueue", lambda song_id, filename: None)
    monkeypatch.setattr(mp3pm_routes.auth, "current_user_id", lambda request: None)

    response = router_client.post(
        "/api/mp3pm/import",
        json={"query": "what do you mean", "sound_id": "44032646", "artist": "ZDS"},
    )
    assert response.status_code == 201
    song = response.json()
    assert song["status"] == "pending"
    assert calls["title"] == "What Do You Mean?"
    assert calls["artist"] == "ZDS"
    # The permanent copy stays in the music folder, and the app copy is in audio/.
    assert (tmp_path / "music" / "ZDS - What Do You Mean.mp3").exists()
    assert (mp3pm_routes.AUDIO_DIR / "abc123.mp3").exists()


def test_import_route_refuses_an_unknown_sound(router_client, monkeypatch):
    monkeypatch.setattr(mp3pm_routes.mp3pm, "find", lambda query, sound_id: None)
    response = router_client.post(
        "/api/mp3pm/import",
        json={"query": "what do you mean", "sound_id": "00000000"},
    )
    assert response.status_code == 404
