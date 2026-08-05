"""API-level tests. Analysis runs for real, so these are slower than the rest."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory, monkeypatch_session):
    data_dir = tmp_path_factory.mktemp("api-data")
    monkeypatch_session.setenv("CHORDSMITH_DATA_DIR", str(data_dir))

    # Config reads the environment at import time, so it has to be reloaded
    # after the override rather than before.
    import importlib

    from app import config, storage

    importlib.reload(config)
    importlib.reload(storage)
    from app import jobs, main
    from app.routes import songs as songs_routes

    importlib.reload(jobs)
    importlib.reload(songs_routes)
    importlib.reload(main)

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def monkeypatch_session():
    from _pytest.monkeypatch import MonkeyPatch

    patcher = MonkeyPatch()
    yield patcher
    patcher.undo()


def upload(client, path, **fields):
    with open(path, "rb") as handle:
        return client.post(
            "/api/songs", files={"file": (path.name, handle, "audio/wav")}, data=fields
        )


def wait_until_ready(client, song_id, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        song = client.get(f"/api/songs/{song_id}").json()
        if song["status"] in ("ready", "failed"):
            return song
        time.sleep(0.5)
    raise AssertionError(f"analysis of {song_id} did not finish within {timeout}s")


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert ".mp3" in body["supportedFormats"]


def test_upload_analyse_and_fetch(client, chord_track):
    response = upload(client, chord_track, artist="Test Band")
    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "pending"
    assert created["artist"] == "Test Band"
    assert created["title"] == "chords"  # derived from the filename

    song = wait_until_ready(client, created["id"])
    assert song["status"] == "ready", song["error"]
    assert song["keyName"] == "G major"
    assert song["analysis"]["beatsPerBar"] == 4
    assert set(song["analysis"]["uniqueChords"]) >= {"G", "D", "Em", "C"}


def test_library_lists_and_filters(client):
    songs = client.get("/api/songs").json()["songs"]
    assert songs
    assert client.get("/api/songs?search=chords").json()["songs"]
    assert client.get("/api/songs?search=nothingmatchesthis").json()["songs"] == []


def test_audio_range_requests(client):
    song_id = client.get("/api/songs").json()["songs"][0]["id"]

    full = client.get(f"/api/songs/{song_id}/audio")
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"

    partial = client.get(f"/api/songs/{song_id}/audio", headers={"Range": "bytes=0-1023"})
    assert partial.status_code == 206
    assert len(partial.content) == 1024
    assert partial.headers["content-range"].startswith("bytes 0-1023/")

    suffix = client.get(f"/api/songs/{song_id}/audio", headers={"Range": "bytes=-512"})
    assert suffix.status_code == 206
    assert len(suffix.content) == 512

    beyond = client.get(f"/api/songs/{song_id}/audio", headers={"Range": "bytes=99999999-"})
    assert beyond.status_code == 416

    malformed = client.get(f"/api/songs/{song_id}/audio", headers={"Range": "chunks=0-10"})
    assert malformed.status_code == 400


def test_midi_export(client):
    song_id = client.get("/api/songs").json()["songs"][0]["id"]
    response = client.get(f"/api/songs/{song_id}/midi?transpose=2")
    assert response.status_code == 200
    assert response.content[:4] == b"MThd"
    assert "attachment" in response.headers["content-disposition"]


def test_midi_rejects_an_out_of_range_transposition(client):
    song_id = client.get("/api/songs").json()["songs"][0]["id"]
    assert client.get(f"/api/songs/{song_id}/midi?transpose=25").status_code == 422


def test_theory_endpoints(client):
    vocabulary = client.get("/api/theory/vocabulary").json()
    assert len(vocabulary["chords"]) == 12 * len(vocabulary["qualities"])

    transposed = client.get("/api/theory/transpose?labels=G,D,Em,C&semitones=2&capo=2").json()
    assert transposed["sounding"] == ["A", "E", "F#m", "D"]
    assert transposed["shapes"] == ["G", "D", "Em", "C"]

    assert client.get("/api/theory/transpose?labels=").status_code == 400


def test_unknown_song_is_a_404(client):
    assert client.get("/api/songs/doesnotexist").status_code == 404
    assert client.delete("/api/songs/doesnotexist").status_code == 404
    assert client.post("/api/songs/doesnotexist/reanalyze").status_code == 404


def test_unsupported_file_type_is_rejected(client, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not audio")
    response = upload(client, path)
    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


def test_empty_upload_is_rejected(client, tmp_path):
    path = tmp_path / "empty.wav"
    path.write_bytes(b"")
    assert upload(client, path).status_code == 400


def test_delete_removes_the_song_and_its_audio(client, chord_track):
    created = upload(client, chord_track).json()
    assert client.delete(f"/api/songs/{created['id']}").status_code == 204
    assert client.get(f"/api/songs/{created['id']}").status_code == 404
