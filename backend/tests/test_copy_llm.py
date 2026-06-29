"""LLM copy backend tests. All HTTP is faked — no real OpenAI/Ollama calls."""
import asyncio

import httpx
import pytest

import app.copy_generators as copy_generators
import app.copy_generators.claude as claude_mod
import app.copy_generators.gemini as gemini_mod
import app.copy_generators.ollama as ollama_mod
import app.copy_generators.openai as openai_mod
from app.copy_generators.claude import ClaudeCopyGenerator
from app.copy_generators.gemini import GeminiCopyGenerator
from app.copy_generators.mock import MockCopyGenerator
from app.copy_generators.ollama import OllamaCopyGenerator
from app.copy_generators.openai import OpenAICopyGenerator
from app.copy_generators.prompt import build_messages, build_system_and_user


class _FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def _client_factory(*, response=None, raise_exc=None):
    """Build a fake httpx.AsyncClient class that captures the POST and returns a
    canned response (or raises)."""
    captured = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            if raise_exc is not None:
                raise raise_exc
            return response

    return _FakeClient, captured


def _run(coro):
    return asyncio.run(coro)


def _gen(adapter):
    return adapter.generate(
        copy_id="c1",
        copy_type="instagram_caption",
        tone="playful",
        audience="gen z shoppers",
        prompt="neon water bottle",
        product_context="Product image: bottle.png",
    )


# --- prompt builder ----------------------------------------------------------
def test_build_messages_includes_all_fields():
    messages = build_messages(
        copy_type="facebook_ad",
        tone="bold",
        audience="runners",
        prompt="trail shoe",
        product_context="Ad scene: shoe on a mountain trail",
    )
    assert messages[0]["role"] == "system"
    assert "bold" in messages[0]["content"]
    user = messages[1]["content"]
    assert "runners" in user
    assert "trail shoe" in user
    assert "shoe on a mountain trail" in user


# --- OpenAI ------------------------------------------------------------------
def test_openai_success(monkeypatch):
    resp = _FakeResp(json_data={"choices": [{"message": {"content": " Buy now! "}}]})
    client_cls, captured = _client_factory(response=resp)
    monkeypatch.setattr(openai_mod.httpx, "AsyncClient", client_cls)

    result = _run(_gen(OpenAICopyGenerator(api_key="sk-test", model="gpt-x")))
    assert result.result_text == "Buy now!"
    assert captured["json"]["model"] == "gpt-x"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"


def test_openai_missing_key_raises(monkeypatch):
    # Should fail before any HTTP call.
    called = {"hit": False}

    class _Boom:
        def __init__(self, *a, **k):
            called["hit"] = True

    monkeypatch.setattr(openai_mod.httpx, "AsyncClient", _Boom)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        _run(_gen(OpenAICopyGenerator(api_key="", model="gpt-x")))
    assert called["hit"] is False


def test_openai_model_unavailable_raises(monkeypatch):
    client_cls, _ = _client_factory(response=_FakeResp(status_code=404, text="no model"))
    monkeypatch.setattr(openai_mod.httpx, "AsyncClient", client_cls)
    with pytest.raises(RuntimeError, match="unavailable"):
        _run(_gen(OpenAICopyGenerator(api_key="sk-test", model="gpt-x")))


def test_openai_empty_response_raises(monkeypatch):
    client_cls, _ = _client_factory(
        response=_FakeResp(json_data={"choices": [{"message": {"content": "   "}}]})
    )
    monkeypatch.setattr(openai_mod.httpx, "AsyncClient", client_cls)
    with pytest.raises(RuntimeError, match="empty"):
        _run(_gen(OpenAICopyGenerator(api_key="sk-test", model="gpt-x")))


def test_openai_timeout_raises(monkeypatch):
    client_cls, _ = _client_factory(raise_exc=httpx.TimeoutException("slow"))
    monkeypatch.setattr(openai_mod.httpx, "AsyncClient", client_cls)
    with pytest.raises(RuntimeError, match="timed out"):
        _run(_gen(OpenAICopyGenerator(api_key="sk-test", model="gpt-x")))


# --- Ollama ------------------------------------------------------------------
def test_ollama_success(monkeypatch):
    resp = _FakeResp(json_data={"message": {"content": "Stop scrolling 🔥"}})
    client_cls, captured = _client_factory(response=resp)
    monkeypatch.setattr(ollama_mod.httpx, "AsyncClient", client_cls)

    result = _run(_gen(OllamaCopyGenerator(base_url="http://x:11434/", model="llama-x")))
    assert result.result_text == "Stop scrolling 🔥"
    assert captured["url"] == "http://x:11434/api/chat"
    assert captured["json"]["model"] == "llama-x"
    assert captured["json"]["stream"] is False


def test_ollama_model_unavailable_raises(monkeypatch):
    client_cls, _ = _client_factory(response=_FakeResp(status_code=404, text="not found"))
    monkeypatch.setattr(ollama_mod.httpx, "AsyncClient", client_cls)
    with pytest.raises(RuntimeError, match="ollama pull"):
        _run(_gen(OllamaCopyGenerator(base_url="http://x:11434", model="llama-x")))


def test_ollama_empty_response_raises(monkeypatch):
    client_cls, _ = _client_factory(response=_FakeResp(json_data={"message": {"content": ""}}))
    monkeypatch.setattr(ollama_mod.httpx, "AsyncClient", client_cls)
    with pytest.raises(RuntimeError, match="empty"):
        _run(_gen(OllamaCopyGenerator(base_url="http://x:11434", model="llama-x")))


def test_ollama_connect_error_raises(monkeypatch):
    client_cls, _ = _client_factory(raise_exc=httpx.ConnectError("refused"))
    monkeypatch.setattr(ollama_mod.httpx, "AsyncClient", client_cls)
    with pytest.raises(RuntimeError, match="reach Ollama"):
        _run(_gen(OllamaCopyGenerator(base_url="http://x:11434", model="llama-x")))


# --- Claude ------------------------------------------------------------------
def test_build_system_and_user_splits_messages():
    system, user = build_system_and_user(
        copy_type="seo_title",
        tone="luxury",
        audience="collectors",
        prompt="leather wallet",
        product_context=None,
    )
    assert "copywriter" in system
    assert "collectors" in user
    assert "leather wallet" in user


def test_claude_success(monkeypatch):
    resp = _FakeResp(json_data={"content": [{"type": "text", "text": "Buy now."}]})
    client_cls, captured = _client_factory(response=resp)
    monkeypatch.setattr(claude_mod.httpx, "AsyncClient", client_cls)

    result = _run(_gen(ClaudeCopyGenerator(api_key="sk-ant", model="claude-x")))
    assert result.result_text == "Buy now."
    assert captured["json"]["model"] == "claude-x"
    assert captured["json"]["system"]
    assert captured["headers"]["x-api-key"] == "sk-ant"


def test_claude_missing_key_raises(monkeypatch):
    called = {"hit": False}

    class _Boom:
        def __init__(self, *a, **k):
            called["hit"] = True

    monkeypatch.setattr(claude_mod.httpx, "AsyncClient", _Boom)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        _run(_gen(ClaudeCopyGenerator(api_key="", model="claude-x")))
    assert called["hit"] is False


def test_claude_empty_response_raises(monkeypatch):
    client_cls, _ = _client_factory(response=_FakeResp(json_data={"content": []}))
    monkeypatch.setattr(claude_mod.httpx, "AsyncClient", client_cls)
    with pytest.raises(RuntimeError, match="empty"):
        _run(_gen(ClaudeCopyGenerator(api_key="sk-ant", model="claude-x")))


# --- Gemini ------------------------------------------------------------------
def test_gemini_success(monkeypatch):
    resp = _FakeResp(
        json_data={"candidates": [{"content": {"parts": [{"text": "Shop the look."}]}}]}
    )
    client_cls, captured = _client_factory(response=resp)
    monkeypatch.setattr(gemini_mod.httpx, "AsyncClient", client_cls)

    result = _run(_gen(GeminiCopyGenerator(api_key="g-key", model="gemini-x")))
    assert result.result_text == "Shop the look."
    assert "gemini-x:generateContent" in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "g-key"


def test_gemini_missing_key_raises(monkeypatch):
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        _run(_gen(GeminiCopyGenerator(api_key="", model="gemini-x")))


def test_gemini_empty_response_raises(monkeypatch):
    client_cls, _ = _client_factory(response=_FakeResp(json_data={"candidates": []}))
    monkeypatch.setattr(gemini_mod.httpx, "AsyncClient", client_cls)
    with pytest.raises(RuntimeError, match="empty"):
        _run(_gen(GeminiCopyGenerator(api_key="g-key", model="gemini-x")))


# --- factory -----------------------------------------------------------------
def test_factory_selects_backend(monkeypatch):
    monkeypatch.setattr(copy_generators, "COPY_BACKEND", "openai")
    assert isinstance(copy_generators.get_copy_generator(), OpenAICopyGenerator)
    monkeypatch.setattr(copy_generators, "COPY_BACKEND", "ollama")
    assert isinstance(copy_generators.get_copy_generator(), OllamaCopyGenerator)
    monkeypatch.setattr(copy_generators, "COPY_BACKEND", "claude")
    assert isinstance(copy_generators.get_copy_generator(), ClaudeCopyGenerator)
    monkeypatch.setattr(copy_generators, "COPY_BACKEND", "gemini")
    assert isinstance(copy_generators.get_copy_generator(), GeminiCopyGenerator)
    # local-qwen / local-deepseek are Ollama presets.
    monkeypatch.setattr(copy_generators, "COPY_BACKEND", "local-qwen")
    gen = copy_generators.get_copy_generator()
    assert isinstance(gen, OllamaCopyGenerator)
    assert gen.model == copy_generators.OLLAMA_QWEN_MODEL
    monkeypatch.setattr(copy_generators, "COPY_BACKEND", "local-deepseek")
    assert copy_generators.get_copy_generator().model == copy_generators.OLLAMA_DEEPSEEK_MODEL
    # Unknown / unset falls back to mock.
    monkeypatch.setattr(copy_generators, "COPY_BACKEND", "mock")
    assert isinstance(copy_generators.get_copy_generator(), MockCopyGenerator)
    monkeypatch.setattr(copy_generators, "COPY_BACKEND", "banana")
    assert isinstance(copy_generators.get_copy_generator(), MockCopyGenerator)
