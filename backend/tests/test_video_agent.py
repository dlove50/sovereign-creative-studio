"""Video agent script writer (fake Ollama) and its API."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import video_agent as va


@pytest.fixture(scope="module", autouse=True)
def _app_ready():
    with TestClient(app):
        yield


def _fake_ollama(monkeypatch, content: str, status: int = 200, calls=None):
    calls = calls if calls is not None else []

    def fake_post(url, **kw):
        calls.append((url, kw.get("json")))
        if url.endswith("/free"):
            return httpx.Response(200, json={})
        return httpx.Response(status, json={"message": {"content": content}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(va.httpx, "post", fake_post)
    monkeypatch.setattr("app.services.voice.httpx.post", fake_post)
    return calls


def test_writes_script_and_frees_gpu_both_ways(monkeypatch):
    calls = _fake_ollama(monkeypatch, json.dumps({"title": "Faster email", "script": "Here is my tip. Reply twice a day."}))
    out = va.write_script("tips about email", 30, model="qwen3:4b")
    assert out == {"title": "Faster email", "script": "Here is my tip. Reply twice a day.", "model": "qwen3:4b", "target_words": 75}
    assert calls[0][0].endswith("/free")  # ComfyUI freed before Ollama loads
    body = calls[-1][1]
    assert body["keep_alive"] == 0 and body["think"] is False and body["format"] == "json"
    assert "about 75 words" in body["messages"][1]["content"]


def test_strips_stage_directions_markup_and_emoji(monkeypatch):
    _fake_ollama(monkeypatch, json.dumps({"title": "t", "script": "[Smiles] **Hello** there 👋 (pause) friends."}))
    assert va.write_script("hi", 15)["script"] == "Hello there friends."


def test_plain_text_reply_still_becomes_a_script(monkeypatch):
    _fake_ollama(monkeypatch, "Just say hello to everyone.")
    out = va.write_script("greeting video", 15)
    assert out["script"] == "Just say hello to everyone." and out["title"] == "greeting video"


def test_missing_model_gives_pull_instruction(monkeypatch):
    _fake_ollama(monkeypatch, "", status=404)
    with pytest.raises(RuntimeError, match="ollama pull"):
        va.write_script("x y z", 30, model="nope:1b")


def test_api_returns_script_and_validates_input(monkeypatch):
    _fake_ollama(monkeypatch, json.dumps({"title": "T", "script": "Spoken words."}))
    c = TestClient(app)
    assert c.post("/api/video-agent/script", json={"prompt": "hi"}).status_code == 422  # too short
    assert c.post("/api/video-agent/script", json={"prompt": "a launch video", "seconds": 999}).status_code == 422
    assert c.post("/api/auth/signup", json={"username": "agent_user", "password": "agentpass1", "name": "A"}).status_code == 201
    r = c.post("/api/video-agent/script", json={"prompt": "a launch video", "seconds": 20})
    assert r.status_code == 200, r.text
    assert r.json()["script"] == "Spoken words." and r.json()["target_words"] == 50


def test_api_reports_ollama_down_as_503(monkeypatch):
    def down(url, **kw):
        if url.endswith("/free"):
            return httpx.Response(200, json={})
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(va.httpx, "post", down)
    monkeypatch.setattr("app.services.voice.httpx.post", down)
    c = TestClient(app)
    c.post("/api/auth/signup", json={"username": "agent_down", "password": "agentpass1", "name": "B"})
    r = c.post("/api/video-agent/script", json={"prompt": "a launch video"})
    assert r.status_code == 503 and "Start Ollama" in r.json()["detail"]
