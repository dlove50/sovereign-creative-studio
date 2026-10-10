import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import cinematic_planner as planner


@pytest.fixture
def plan():
    return {"title": "Home", "synopsis": "A traveler returns home.",
            "characters": [{"id": "traveler", "name": "Jo", "description": "Blue coat"}],
            "locations": [{"id": "station", "name": "Station", "description": "Quiet platform"}],
            "shots": [{"id": "arrival", "duration_seconds": 10, "location_id": "station",
                       "character_ids": ["traveler"], "description": "Jo exits a train.",
                       "camera": "Wide static shot", "dialogue": [{"character_id": "traveler", "text": "Home."}],
                       "narration": "", "transition": "Cut", "image_prompt": "Jo in blue coat on a platform",
                       "video_prompt": "Jo exits the train onto the quiet platform."}]}


def fake_ollama(monkeypatch, content, busy=False, status=200):
    calls = []
    monkeypatch.setattr(planner.httpx, "get", lambda *args, **kwargs: httpx.Response(
        200, json={"queue_running": [1] if busy else [], "queue_pending": []},
        request=httpx.Request("GET", "http://local/queue")))

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return httpx.Response(status, json={"message": {"content": content}})

    monkeypatch.setattr(planner.httpx, "post", post)
    return calls


def test_valid_plan_uses_configured_model_and_schema(monkeypatch, plan):
    monkeypatch.setattr(planner.config, "VIDEO_AGENT_MODEL", "local:test")
    calls = fake_ollama(monkeypatch, json.dumps(plan))
    result = planner.write_plan("A traveler returns home", 10)
    assert result == {**plan, "model": "local:test"}
    assert len(calls) == 1
    url, body = calls[0]
    assert url.endswith("/api/chat")
    assert body["format"]["additionalProperties"] is False
    assert body["model"] == "local:test" and body["keep_alive"] == 0


def test_busy_comfy_keeps_gpu_and_never_receives_free_request(monkeypatch, plan):
    calls = fake_ollama(monkeypatch, json.dumps(plan), busy=True)
    planner.write_plan("Traveler returns home", 10)
    assert len(calls) == 1
    assert calls[0][1]["options"]["num_gpu"] == 0


def test_planner_origin_override_keeps_other_ollama_configuration(monkeypatch, plan):
    monkeypatch.setenv("VIDEO_AGENT_OLLAMA_BASE_URL", "http://127.0.0.1:11435/")
    previous = planner.config.OLLAMA_BASE_URL
    calls = fake_ollama(monkeypatch, json.dumps(plan))
    planner.write_plan("Traveler returns home", 10)
    assert calls[0][0] == "http://127.0.0.1:11435/api/chat"
    assert planner.config.OLLAMA_BASE_URL == previous


def test_unknown_comfy_state_uses_cpu(monkeypatch, plan):
    calls = fake_ollama(monkeypatch, json.dumps(plan))
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(planner.httpx, "get", unavailable)
    planner.write_plan("Traveler returns home", 10)
    assert calls[0][1]["options"]["num_gpu"] == 0


@pytest.mark.parametrize("fault", ["location", "character", "dialogue", "duplicate", "duration", "extra", "wrong_type"])
def test_invalid_structured_plan_is_rejected(monkeypatch, plan, fault):
    broken = copy.deepcopy(plan)
    shot = broken["shots"][0]
    if fault == "location": shot["location_id"] = "missing"
    if fault == "character": shot["character_ids"] = ["missing"]
    if fault == "dialogue": shot["dialogue"][0]["character_id"] = "missing"
    if fault == "duplicate": broken["locations"].append(broken["locations"][0])
    if fault == "duration": shot["duration_seconds"] = 11
    if fault == "extra": shot["unexpected"] = True
    if fault == "wrong_type": shot["duration_seconds"] = "10"
    fake_ollama(monkeypatch, json.dumps(broken))
    with pytest.raises(RuntimeError, match="invalid cinematic plan"):
        planner.write_plan("Traveler returns home", 10)


@pytest.mark.parametrize("content", ["not JSON", "{}", "[]", "null"])
def test_malformed_model_output_is_actionable(monkeypatch, content):
    fake_ollama(monkeypatch, content)
    with pytest.raises(RuntimeError, match="Retry planning"):
        planner.write_plan("Traveler returns home", 10)


def test_missing_model_instructs_local_install(monkeypatch):
    fake_ollama(monkeypatch, "", status=404)
    with pytest.raises(RuntimeError, match="ollama pull"):
        planner.write_plan("Traveler returns home", 10)


def test_plan_endpoint_validates_and_uses_auth_dependency(monkeypatch, plan):
    from app.deps import get_current_user
    calls = fake_ollama(monkeypatch, json.dumps(plan))
    auth_calls = []
    def user():
        auth_calls.append(True)
        return object()
    app.dependency_overrides[get_current_user] = user
    try:
        with TestClient(app) as client:
            result = client.post("/api/video-agent/plan", json={"prompt": "Traveler returns home", "seconds": 10})
            assert result.status_code == 200, result.text
            assert result.json()["shots"][0]["id"] == "arrival"
            assert auth_calls
            assert client.post("/api/video-agent/plan", json={"prompt": "Traveler", "seconds": 181}).status_code == 422
            assert len(calls) == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)
