"""Prompt assist: clean up a prompt, write one from an idea, and write a movie as bible + chapters (model faked)."""
import json
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
from app.services import prompt_assist as pa  # noqa: E402

MOVIE = {
    "title": "The Last Bite", "logline": "A chef wins over a critic.", "look": "Warm cinematic drama, 16:9",
    "cast": [{"name": "Elena", "identity": "60s, silver hair", "wardrobe": "denim apron"}],
    "rules": "Natural action, coherent cuts, no text", "sound": "city ambience",
    "chapters": [
        {"title": "Opening Day", "seconds": 20, "beats": "Elena opens the truck. Close-up of the grill.", "guards": "no customers yet"},
        {"title": "The Critic", "seconds": 2, "beats": "The critic tastes the food and smiles.", "guards": ""},
        {"title": "", "seconds": 5, "beats": "dropped: no title", "guards": ""},
    ],
}


@pytest.fixture()
def model(monkeypatch):
    calls = []

    def fake(messages, schema, timeout=240.0, **kwargs):
        calls.append({"system": messages[0]["content"], "user": messages[1]["content"], "schema": schema})
        if "chapters" in schema.get("properties", {}):
            return json.dumps(MOVIE)
        return json.dumps({"text": "  A clean, organised request.  "})

    monkeypatch.setattr(pa, "_ollama_chat", fake)
    return calls


def test_clean_keeps_ideas_and_returns_tidy_text(model):
    with TestClient(app) as c:
        out = c.post("/api/prompt-assist/clean", json={"text": "uh so like a song about my dog", "kind": "song_idea"})
        assert out.status_code == 200 and out.json()["text"] == "A clean, organised request."
        assert "Keep EVERY idea" in model[0]["system"] and "uh so like a song about my dog" in model[0]["user"]


def test_write_uses_the_guide_for_the_kind(model):
    with TestClient(app) as c:
        out = c.post("/api/prompt-assist/write", json={"idea": "my dog Max", "kind": "lyrics", "context": "Music Lab"})
        assert out.status_code == 200
        assert "[verse]" in model[0]["system"] and "Music Lab" in model[0]["system"]
        unknown = c.post("/api/prompt-assist/write", json={"idea": "x", "kind": "not-a-kind"})
        assert unknown.status_code == 200  # falls back to the general guide


def test_movie_is_a_bible_and_titled_chapters(model):
    with TestClient(app) as c:
        out = c.post("/api/prompt-assist/movie", json={"idea": "a chef and a critic", "seconds": 60})
        assert out.status_code == 200, out.text
        plan, text = out.json()["plan"], out.json()["text"]
        assert [ch["title"] for ch in plan["chapters"]] == ["Opening Day", "The Critic"]  # untitled chapter dropped
        assert plan["chapters"][0]["seconds"] == 15 and plan["chapters"][1]["seconds"] == 3  # clamped to 3..15
        assert "BIBLE" in text and "Elena: 60s, silver hair. Wardrobe: denim apron." in text and "1. Opening Day (15 s)" in text
        system = model[0]["system"]
        assert "4 titled chapters" in system and "about 60 seconds" in system and "jungle" not in system.lower()


def test_empty_input_and_model_failures_are_explained(model, monkeypatch):
    with TestClient(app) as c:
        assert c.post("/api/prompt-assist/clean", json={"text": ""}).status_code == 422
        monkeypatch.setattr(pa, "_ollama_chat", lambda *a, **k: "not json")
        bad = c.post("/api/prompt-assist/write", json={"idea": "x"})
        assert bad.status_code == 502 and "unusable" in bad.json()["detail"]
