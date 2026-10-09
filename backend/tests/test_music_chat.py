"""Music Lab songwriting chat: one turn returns a reply plus the full current song."""
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
from app.services import music_compose  # noqa: E402

DRAFT = {
    "reply": "Here is a first draft about the bay at sunrise.",
    "title": "Bay Sunrise",
    "style": "reggae, warm male vocal",
    "lyrics": "[verse]\nThe light comes over the water\nGold on the morning tide\n[chorus]\nEasy, easy sunrise\nCarry me to your side",
}


@pytest.fixture()
def seen(monkeypatch):
    calls = []

    def fake(messages, schema, timeout=240.0):
        calls.append(messages)
        return json.dumps(DRAFT)

    monkeypatch.setattr(music_compose, "_ollama_chat", fake)
    return calls


def test_first_turn_writes_a_draft(seen):
    with TestClient(app) as c:
        out = c.post("/api/music/lyrics-chat", json={"messages": [{"role": "user", "content": "A reggae song about sunrise at the bay"}]})
        assert out.status_code == 200, out.text
        body = out.json()
        assert body["title"] == "Bay Sunrise" and "[chorus]" in body["lyrics"] and body["reply"]
        assert "There is no song yet" in seen[0][0]["content"]


def test_later_turn_sends_the_current_song_and_history(seen):
    with TestClient(app) as c:
        out = c.post("/api/music/lyrics-chat", json={
            "messages": [
                {"role": "user", "content": "A reggae song about sunrise"},
                {"role": "assistant", "content": "Here is a draft."},
                {"role": "user", "content": "Make the chorus sadder"},
            ],
            "current": {"title": "Bay Sunrise", "style": "reggae", "lyrics": DRAFT["lyrics"]},
        })
        assert out.status_code == 200, out.text
        system = seen[0][0]["content"]
        assert "The song so far" in system and "Bay Sunrise" in system and "Gold on the morning tide" in system
        assert [m["role"] for m in seen[0][1:]] == ["user", "assistant", "user"]


def test_bad_requests_are_rejected(seen):
    with TestClient(app) as c:
        assert c.post("/api/music/lyrics-chat", json={"messages": []}).status_code == 422
        assert c.post("/api/music/lyrics-chat", json={"messages": [{"role": "system", "content": "x"}]}).status_code == 422
        last_is_assistant = c.post("/api/music/lyrics-chat", json={"messages": [{"role": "assistant", "content": "hi"}]})
        assert last_is_assistant.status_code == 502 and "what you want" in last_is_assistant.json()["detail"]
        assert not seen


def test_unusable_model_output_is_a_clean_error(monkeypatch):
    monkeypatch.setattr(music_compose, "_ollama_chat", lambda *a, **k: "not json at all")
    with TestClient(app) as c:
        out = c.post("/api/music/lyrics-chat", json={"messages": [{"role": "user", "content": "a song"}]})
        assert out.status_code == 502 and "unusable" in out.json()["detail"]
