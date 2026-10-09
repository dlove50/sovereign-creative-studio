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

    def fake(messages, schema, timeout=240.0, **kwargs):
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


def _edit_request(c):
    return c.post("/api/music/lyrics-chat", json={
        "messages": [{"role": "user", "content": "A reggae song"}, {"role": "assistant", "content": "Draft."}, {"role": "user", "content": "Make the chorus sadder"}],
        "current": {"title": "Bay Sunrise", "style": "reggae", "lyrics": DRAFT["lyrics"]},
    })


def test_an_unchanged_edit_is_retried_once(monkeypatch):
    answers = [dict(DRAFT, reply="Made it sadder."), dict(DRAFT, reply="Rewritten.", lyrics=DRAFT["lyrics"].replace("Easy, easy sunrise", "Gone, gone is the sunrise"))]
    asked = []

    def fake(messages, schema, timeout=240.0, **kwargs):
        asked.append(messages[0]["content"])
        return json.dumps(answers[len(asked) - 1])

    monkeypatch.setattr(music_compose, "_ollama_chat", fake)
    with TestClient(app) as c:
        out = _edit_request(c)
        assert out.status_code == 200, out.text
        assert len(asked) == 2 and "IDENTICAL" in asked[1]
        assert "Gone, gone" in out.json()["lyrics"] and out.json()["reply"] == "Rewritten."


def test_a_model_that_keeps_returning_the_same_words_is_reported_honestly(monkeypatch):
    monkeypatch.setattr(music_compose, "_ollama_chat", lambda *a, **k: json.dumps(dict(DRAFT, reply="Made it sadder.")))
    with TestClient(app) as c:
        body = _edit_request(c).json()
        assert body["lyrics"] == DRAFT["lyrics"] and "could not change" in body["reply"]


def test_line_budget_follows_song_length():
    assert music_compose.lyric_line_budget(60) == 8
    assert music_compose.lyric_line_budget(120) == 15
    assert music_compose.lyric_line_budget(210) == 26
    assert music_compose.lyric_line_budget(30) == 6 and music_compose.lyric_line_budget(900) == 32
    assert music_compose.count_lines("[verse]\nOne\n\nTwo\n[chorus]\nThree") == 3


def test_the_chat_prompt_carries_the_song_length(seen):
    with TestClient(app) as c:
        out = c.post("/api/music/lyrics-chat", json={"messages": [{"role": "user", "content": "A reggae song"}], "duration": 120})
        assert out.status_code == 200, out.text
        assert "about 15 sung lines" in seen[0][0]["content"] and "2 minutes long" in seen[0][0]["content"]


def test_lyrics_far_over_budget_are_cut_once(monkeypatch):
    long_lyrics = "[verse]\n" + "\n".join(f"A long line number {i} of the song" for i in range(30))
    short_lyrics = "[verse]\n" + "\n".join(f"A short line number {i}" for i in range(12))
    answers = [dict(DRAFT, lyrics=long_lyrics), dict(DRAFT, lyrics=short_lyrics, reply="Trimmed it.")]
    asked = []

    def fake(messages, schema, timeout=240.0, **kwargs):
        asked.append(messages[0]["content"])
        return json.dumps(answers[len(asked) - 1])

    monkeypatch.setattr(music_compose, "_ollama_chat", fake)
    with TestClient(app) as c:
        body = c.post("/api/music/lyrics-chat", json={"messages": [{"role": "user", "content": "A reggae song"}], "duration": 120}).json()
        assert len(asked) == 2 and "at most 18" in asked[1]
        assert music_compose.count_lines(body["lyrics"]) == 12 and body["reply"] == "Trimmed it."
