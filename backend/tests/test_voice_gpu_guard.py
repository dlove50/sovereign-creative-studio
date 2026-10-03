"""Do not evict active ComfyUI work to make room for a speech/LLM job."""
import httpx
import pytest

from app.services import voice


@pytest.mark.parametrize("running,pending", [([1], []), ([], [1]), ([1], [2])])
def test_busy_renderer_is_not_unloaded(monkeypatch, running, pending):
    monkeypatch.setattr(voice.httpx, "get", lambda *a, **k: httpx.Response(200, json={"queue_running": running, "queue_pending": pending}, request=httpx.Request("GET", "http://renderer/queue")))
    calls = []
    monkeypatch.setattr(voice.httpx, "post", lambda *a, **k: calls.append((a, k)))
    with pytest.raises(RuntimeError, match="render GPU is busy"):
        voice._free_comfyui_vram()
    assert not calls


def test_idle_renderer_can_unload(monkeypatch):
    monkeypatch.setattr(voice.httpx, "get", lambda *a, **k: httpx.Response(200, json={"queue_running": [], "queue_pending": []}, request=httpx.Request("GET", "http://renderer/queue")))
    calls = []
    monkeypatch.setattr(voice.httpx, "post", lambda *a, **k: calls.append(k))
    voice._free_comfyui_vram()
    assert calls == [{"json": {"unload_models": True, "free_memory": True}, "timeout": 10.0}]


@pytest.mark.parametrize("data", [{}, {"queue_running": None, "queue_pending": []}, []])
def test_unknown_queue_is_not_unloaded(monkeypatch, data):
    monkeypatch.setattr(voice.httpx, "get", lambda *a, **k: httpx.Response(200, json=data, request=httpx.Request("GET", "http://renderer/queue")))
    calls = []
    monkeypatch.setattr(voice.httpx, "post", lambda *a, **k: calls.append(k))
    with pytest.raises(RuntimeError, match="Cannot verify"):
        voice._free_comfyui_vram()
    assert not calls


def test_offline_renderer_needs_no_unload(monkeypatch):
    def offline(*args, **kwargs):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(voice.httpx, "get", offline)
    voice._free_comfyui_vram()


def test_timeout_does_not_assume_idle(monkeypatch):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("busy")
    monkeypatch.setattr(voice.httpx, "get", timeout)
    with pytest.raises(RuntimeError, match="Cannot check"):
        voice._free_comfyui_vram()
