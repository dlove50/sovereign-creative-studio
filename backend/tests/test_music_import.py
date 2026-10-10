"""Music Lab import: bring your own songs in, split the vocal, transcribe timed lyrics, correct them.

Real ffmpeg converts the test audio; Demucs and Whisper are faked so no GPU or model is needed.
"""
import os
import tempfile
import wave

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.main import app  # noqa: E402
from app.services import music, music_import, stems  # noqa: E402

LINES = [
    {"start": 1.0, "end": 3.5, "text": "Sun comes up over the bay"},
    {"start": 4.0, "end": 6.2, "text": "Warm and easy all the way"},
]


@pytest.fixture(autouse=True)
def isolated_music_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSIC_DIR", tmp_path / "music")
    music_import._jobs.clear()
    yield


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _wav_bytes(tmp_path, seconds=1.0, name="tone.wav"):
    path = tmp_path / name
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x10\x20" * int(22050 * seconds))
    return path.read_bytes()


def _fake_split(tmp_path, monkeypatch):
    def split(song_id, **_kw):
        out = stems.stems_dir(song_id)
        out.mkdir(parents=True, exist_ok=True)
        for name in stems.STEM_NAMES:
            (out / f"{name}.wav").write_bytes(_wav_bytes(tmp_path, name=f"{name}.wav"))
        return {n: stems.stem_path(song_id, n) for n in stems.STEM_NAMES}

    monkeypatch.setattr(stems, "ensure_stems", split)


# --- import -----------------------------------------------------------------------------------

def test_import_converts_audio_into_a_library_song(tmp_path):
    song = music_import.import_song("My Summer Tune.wav", _wav_bytes(tmp_path, seconds=2.0))
    assert song["provider"] == "imported"
    assert song["title"] == "My Summer Tune"
    assert song["source_filename"] == "My Summer Tune.wav"
    assert song["lyrics"] == "" and song["instrumental"] is False
    assert music.audio_path(song["id"]).stat().st_size > 0
    assert music.get_song(song["id"])["id"] == song["id"]
    assert 1.5 <= song["duration_requested"] <= 2.5


def test_import_rejects_unknown_types_empty_and_unreadable_files(tmp_path):
    with pytest.raises(music.MusicError, match="MP3, WAV"):
        music_import.import_song("notes.txt", b"hello")
    with pytest.raises(music.MusicError, match="empty"):
        music_import.import_song("song.mp3", b"")
    with pytest.raises(music.MusicError, match="Could not read"):
        music_import.import_song("song.wav", b"this is not audio at all")
    assert music.list_songs() == []


def test_import_api_takes_several_files_and_reports_each(client, tmp_path):
    files = [
        ("files", ("one.wav", _wav_bytes(tmp_path), "audio/wav")),
        ("files", ("two.wav", _wav_bytes(tmp_path), "audio/wav")),
        ("files", ("bad.txt", b"nope", "text/plain")),
    ]
    r = client.post("/api/music/import", files=files)
    assert r.status_code == 200
    body = r.json()
    assert sorted(s["title"] for s in body["songs"]) == ["one", "two"]
    assert all(s["audio_url"].endswith("/audio") for s in body["songs"])
    assert body["errors"][0]["filename"] == "bad.txt"


# --- lyrics transcription ---------------------------------------------------------------------

def test_transcribing_an_imported_song_saves_timed_lines_and_the_lyrics(tmp_path, monkeypatch):
    _fake_split(tmp_path, monkeypatch)
    heard = []
    monkeypatch.setattr(music_import, "transcribe_lines", lambda path: heard.append(path.name) or LINES)
    song = music_import.import_song("bay.wav", _wav_bytes(tmp_path))
    job = music_import.start_transcription(song["id"], run_in_background=False)
    assert job["status"] == "done" and job["stage"] == "done"
    assert heard == ["vocals.wav"]  # Whisper listens to the isolated vocal, not the full mix
    saved = music.get_song(song["id"])
    assert saved["lyric_lines"] == LINES
    assert saved["lyrics"] == "Sun comes up over the bay\nWarm and easy all the way"
    assert saved["lyrics_source"] == "whisper"


def test_transcribing_keeps_lyrics_you_wrote_for_a_made_song(tmp_path, monkeypatch):
    _fake_split(tmp_path, monkeypatch)
    monkeypatch.setattr(music_import, "transcribe_lines", lambda path: LINES)
    made = music._save_song(_wav_bytes(tmp_path), dict(title="Made", style="reggae", lyrics="[verse]\nmy words",
                                                      instrumental=False, duration=30.0, seed=1, quality="V0"), 1.0)
    music_import.start_transcription(made["id"], run_in_background=False)
    saved = music.get_song(made["id"])
    assert saved["lyrics"] == "[verse]\nmy words"
    assert saved["lyric_lines"] == LINES


def test_a_failed_split_or_silent_vocal_is_reported_on_the_job(tmp_path, monkeypatch):
    def broken(song_id, **_kw):
        raise music.MusicError("The vocal splitter (Demucs) is not installed.")

    monkeypatch.setattr(stems, "ensure_stems", broken)
    song = music_import.import_song("x.wav", _wav_bytes(tmp_path))
    job = music_import.start_transcription(song["id"], run_in_background=False)
    assert job["status"] == "error" and "Demucs" in job["error"]

    _fake_split(tmp_path, monkeypatch)
    monkeypatch.setattr(music_import, "transcribe_lines", lambda path: [])
    job = music_import.start_transcription(song["id"], run_in_background=False)
    assert job["status"] == "error" and "No singing" in job["error"]


def test_transcribe_api_starts_a_job_and_reports_it(client, tmp_path, monkeypatch):
    _fake_split(tmp_path, monkeypatch)
    monkeypatch.setattr(music_import, "transcribe_lines", lambda path: LINES)
    monkeypatch.setattr(music_import, "_spawn", lambda fn, *args: fn(*args))  # run the job inline
    song = music_import.import_song("bay.wav", _wav_bytes(tmp_path))
    r = client.post(f"/api/music/songs/{song['id']}/transcribe")
    assert r.status_code == 202
    job = client.get(f"/api/music/lyrics-jobs/{r.json()['id']}").json()
    assert job["status"] == "done" and job["song"]["lyric_lines"] == LINES
    assert client.post("/api/music/songs/000000000000/transcribe").status_code == 404
    assert client.get("/api/music/lyrics-jobs/nope").status_code == 404


# --- correcting lyrics ------------------------------------------------------------------------

def test_corrected_lines_are_saved_with_their_timing(client, tmp_path, monkeypatch):
    _fake_split(tmp_path, monkeypatch)
    monkeypatch.setattr(music_import, "transcribe_lines", lambda path: LINES)
    song = music_import.import_song("bay.wav", _wav_bytes(tmp_path))
    music_import.start_transcription(song["id"], run_in_background=False)
    fixed = [{**LINES[0], "text": "Sun comes up across the bay"}, LINES[1]]
    r = client.put(f"/api/music/songs/{song['id']}/lyric-lines", json={"lines": fixed})
    assert r.status_code == 200
    saved = music.get_song(song["id"])
    assert saved["lyric_lines"][0]["text"] == "Sun comes up across the bay"
    assert saved["lyrics"].startswith("Sun comes up across the bay")
    bad = client.put(f"/api/music/songs/{song['id']}/lyric-lines", json={"lines": [{"start": 5, "end": 2, "text": "x"}]})
    assert bad.status_code == 400


# --- vocal waveform ---------------------------------------------------------------------------

def test_vocal_waveform_is_offered_once_the_song_is_split(client, tmp_path, monkeypatch):
    song = music_import.import_song("bay.wav", _wav_bytes(tmp_path))
    r = client.get(f"/api/music/songs/{song['id']}/vocals")
    assert r.status_code == 200 and r.json() == {"has_stems": False, "duration": 0, "peaks": None}
    _fake_split(tmp_path, monkeypatch)
    stems.ensure_stems(song["id"])
    body = client.get(f"/api/music/songs/{song['id']}/vocals").json()
    assert body["has_stems"] is True and body["duration"] > 0 and len(body["peaks"]) > 100
