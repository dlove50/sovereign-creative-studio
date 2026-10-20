"""Real codec conversion and project association; no AI engines or credits required."""
import io
import subprocess
import wave
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import config
from app.deps import get_current_user
from app.main import app
from app.services import music, video_import
from app.services.music_playback import find_ffmpeg_tool


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSIC_DIR", tmp_path / "music")
    with TestClient(app) as client:
        yield client


@pytest.fixture
def footage(tmp_path):
    ffmpeg = find_ffmpeg_tool("ffmpeg")
    assert ffmpeg, "FFmpeg is required for the media import tests"
    path = tmp_path / "existing-edit.mov"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=96x64:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1.2", "-c:v", "libx264", "-c:a", "aac", str(path)],
                   capture_output=True, timeout=30, check=True)
    return path.read_bytes()


def audio():
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(22050)
        stream.writeframes(b"\x10\x20" * 22050)
    return output.getvalue()


def project(client):
    response = client.post("/api/projects", json={"name": "Imported edits"})
    assert response.status_code == 201
    return response.json()["id"]


def test_video_import_converts_and_appears_in_project(client, footage):
    project_id = project(client)
    result = client.post("/api/videos/import", data={"project_id": project_id},
                         files=[("files", ("Existing edit.mov", footage, "video/quicktime")),
                                ("files", ("wrong.txt", b"no", "text/plain"))])
    assert result.status_code == 200
    body = result.json()
    assert len(body["videos"]) == len(body["errors"]) == 1
    video = body["videos"][0]
    assert video["provider"] == "imported"
    assert video["status"] == "completed"
    assert video["credits_cost"] == 0
    assert video["project_id"] == project_id
    assert video["duration_seconds"] == 2
    assert client.get(video["result_url"]).status_code == 200
    stored = config.STORAGE_DIR / "videos" / video["result_url"].rsplit("/", 1)[-1]
    probe = subprocess.run([find_ffmpeg_tool("ffprobe"), "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(stored)],
                           capture_output=True, text=True, check=True)
    assert "h264" in probe.stdout and "aac" in probe.stdout
    workspace = client.get(f"/api/projects/{project_id}/workspace").json()
    assert workspace["video_generations"][0]["title"] == "Existing edit"
    assert workspace["counts_by_type"]["video"] == 1
    assert client.get(f"/api/videos?project_id={project_id}").json()[0]["id"] == video["id"]


def test_music_import_keeps_project_destination(client):
    project_id = project(client)
    result = client.post("/api/music/import", data={"project_id": project_id},
                         files={"files": ("Existing track.wav", audio(), "audio/wav")}).json()
    song = result["songs"][0]
    assert song["project_id"] == project_id
    assert client.get(song["audio_url"]).status_code == 200
    workspace = client.get(f"/api/projects/{project_id}/workspace").json()
    item = workspace["uploaded_assets"][0]
    assert item["source_entity_type"] == "music_song"
    assert item["title"] == "Existing track"
    other = project(client)
    assert client.get(f"/api/projects/{other}/workspace").json()["uploaded_assets"] == []


@pytest.mark.parametrize("endpoint", ["videos", "music"])
def test_import_rejects_another_users_project(client, endpoint):
    project_id = project(client)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="other-user")
    try:
        response = client.post(f"/api/{endpoint}/import", data={"project_id": project_id},
                               files={"files": ("file.mp4", b"invalid", "video/mp4")})
        assert response.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_invalid_and_oversize_video_cleanup(client, monkeypatch):
    project_id = project(client)
    monkeypatch.setattr(video_import, "MAX_BYTES", 3)
    response = client.post("/api/videos/import", data={"project_id": project_id},
                           files={"files": ("huge.mp4", b"12345", "video/mp4")}).json()
    assert response["videos"] == []
    assert "500 MB" in response["errors"][0]["error"]
    monkeypatch.setattr(video_import, "MAX_BYTES", 500 * 1024 * 1024)
    response = client.post("/api/videos/import", data={"project_id": project_id},
                           files={"files": ("bad.mp4", b"invalid", "video/mp4")}).json()
    assert not response["videos"] and response["errors"]
    assert not list((config.STORAGE_DIR / "videos").glob(".import-*"))


def test_music_import_without_project_still_works(client):
    response = client.post("/api/music/import", files={"files": ("track.wav", audio(), "audio/wav")}).json()
    assert len(response["songs"]) == 1
    assert response["songs"][0]["project_id"] is None
    assert len(music.list_songs()) == 1
