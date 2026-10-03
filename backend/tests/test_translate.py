"""Translate videos: subtitle formats, scene grouping, malformed-model handling, and the draft movie."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import translate  # noqa: E402

SEGS = [{"start": 0.0, "end": 1.5, "text": "Hola"}, {"start": 3661.25, "end": 3662.0, "text": "Adios"}]


def test_srt_and_vtt_timestamps():
    srt, vtt = translate.to_srt(SEGS), translate.to_vtt(SEGS)
    assert srt.startswith("1\n00:00:00,000 --> 00:00:01,500\nHola\n")
    assert "2\n01:01:01,250 --> 01:01:02,000\nAdios" in srt
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.500")


def test_split_scenes_never_splits_a_line_and_respects_the_limit():
    lines = ["a" * 500, "b" * 500, "c" * 500, "", "d" * 100]
    scenes = translate.split_scenes(lines, 1200)
    assert [len(s) for s in scenes] == [1001, 601]
    assert all(len(s) <= 1200 for s in scenes)


def test_unknown_language_is_rejected_before_calling_the_model():
    with pytest.raises(RuntimeError, match="listed languages"):
        translate.translate_lines(["hi"], "Klingon")


class _Resp:
    status_code = 200

    def __init__(self, content):
        self._c = content

    def json(self):
        return {"message": {"content": self._c}}


def test_translation_batches_and_checks_line_count(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        n = len(kw["json"]["messages"][1]["content"].splitlines())
        calls.append(n)
        return _Resp('{"lines": [' + ",".join('"t"' for _ in range(n)) + "]}")

    monkeypatch.setattr(translate.httpx, "post", fake_post)
    monkeypatch.setattr(translate, "_free_comfyui_vram", lambda: None)
    assert translate.translate_lines(["x"] * 45, "French") == ["t"] * 45
    assert calls == [20, 20, 5]

    monkeypatch.setattr(translate.httpx, "post", lambda url, **kw: _Resp('{"lines": ["only one"]}'))
    with pytest.raises(RuntimeError, match="malformed"):
        translate.translate_lines(["a", "b"], "French")


def test_translate_endpoint_returns_segments_and_subtitle_files_and_a_draft_movie(monkeypatch):
    monkeypatch.setattr(translate, "transcribe_segments", lambda p: [{"start": 0.0, "end": 2.0, "text": "Hello there"}])
    monkeypatch.setattr(translate, "translate_lines", lambda lines, lang, model=None: ["Hola"])
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "tr_user", "password": "translate1pw", "name": "T"}).status_code == 201
        r = c.post("/api/translate", data={"language": "Spanish"}, files={"file": ("a.wav", b"RIFFxxxx")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["segments"][0]["text"] == "Hola" and body["segments"][0]["original"] == "Hello there"
        assert body["has_video"] is False
        assert c.post("/api/translate", data={"language": "Klingon"}, files={"file": ("a.wav", b"x")}).status_code == 400
        assert c.post("/api/translate", data={"language": "Spanish"}, files={"file": ("a.txt", b"x")}).status_code == 400

        made = c.post("/api/translate/to-movie", json={"lines": ["Hola", "Adios"], "avatar_id": "a1", "title": "Mi video"})
        assert made.status_code == 201
        movie = c.get(f"/api/movies/{made.json()['movie_id']}").json()
        assert movie["status"] == "draft" and movie["scenes"][0]["script"] == "Hola Adios"
