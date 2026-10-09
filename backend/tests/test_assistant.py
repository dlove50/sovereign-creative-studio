"""Studio assistant (safe actions chosen by the local model, carried out by the server) and the developer API list."""
import json
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import assistant  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\nfakeimage"


class Reply:
    def __init__(self, decided=None, content=None, done_reason="stop"):
        self.payload = {"done_reason": done_reason, "message": {"content": content if content is not None else json.dumps(decided)}}

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


@pytest.fixture()
def model(monkeypatch):
    state = {"reply": None, "sent": []}
    monkeypatch.setattr(assistant, "_free_comfyui_vram", lambda: None)

    def post(url, json=None, timeout=None):
        state["sent"].append(json)
        if isinstance(state["reply"], Exception):
            raise state["reply"]
        return state["reply"]

    monkeypatch.setattr(assistant.httpx, "post", post)
    return state


def _signed_in(name):
    c = TestClient(app)
    assert c.post("/api/auth/signup", json={"username": name, "password": "assistpass1", "name": name}).status_code == 201
    return c


def test_assistant_answers_navigates_and_reads_the_users_own_data(model):
    with TestClient(app):
        c = _signed_in("assist_user")
        for name in ("Ada", "Ben"):
            assert c.post("/api/avatars/photo", data={"name": name}, files={"file": ("p.png", PNG, "image/png")}).status_code == 201
        ask = lambda text: c.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": text}]})

        model["reply"] = Reply({"reply": "Batch videos can do that.", "action": "open_page", "page": "Batch videos"})
        out = ask("How do I make many videos?").json()
        assert out["navigate_to"] == "/batch" and out["page"] == "Batch videos" and out["action"] == "open_page"
        sent = model["sent"][-1]
        assert sent["format"]["properties"]["action"]["enum"] == assistant.ACTIONS and sent["think"] is False
        assert "Batch videos: make many videos" in sent["messages"][0]["content"]

        model["reply"] = Reply({"reply": "Let me check.", "action": "show_credits", "page": ""})
        credits = ask("How many credits do I have?").json()
        assert credits["navigate_to"] is None and credits["reply"].startswith("Let me check. You have ") and "credits." in credits["reply"]

        model["reply"] = Reply({"reply": "Here they are.", "action": "list_avatars", "page": ""})
        avatars = ask("Which avatars do I have?").json()["reply"]
        assert "You have 2 avatar looks" in avatars and "Ada" in avatars and "Ben" in avatars
        for number in range(250):  # the count is the real total, not the number of names fetched
            with __import__("app.database", fromlist=["SessionLocal"]).SessionLocal() as db:
                from app.models import AvatarAsset, User
                owner = db.query(User).filter(User.username == "assist_user").one()
                db.add(AvatarAsset(user_id=owner.id, name=f"Extra {number}", avatar_type="photo_avatar", source_file_path="x.png"))
                db.commit()
        assert "You have 252 avatar looks" in ask("Which avatars do I have?").json()["reply"]

        model["reply"] = Reply({"reply": "Nothing yet.", "action": "list_recent_videos", "page": ""})
        assert "no videos yet" in ask("What did I make?").json()["reply"]


def test_assistant_ignores_pages_and_actions_it_may_not_use_and_reports_model_trouble(model):
    with TestClient(app):
        c = _signed_in("assist_guard")
        ask = lambda text="hello": c.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": text}]})
        model["reply"] = Reply({"reply": "Opening it.", "action": "open_page", "page": "/admin/delete-everything"})
        out = ask().json()
        assert out["navigate_to"] is None and out["action"] == "none"
        model["reply"] = Reply({"reply": "Rendering now.", "action": "render_all", "page": ""})
        assert ask().json()["action"] == "none"
        for bad in (Reply(content="not json"), Reply(content="{}"), Reply({"reply": "x", "action": "none", "page": ""}, done_reason="length"),
                    httpx.ConnectError("offline")):
            model["reply"] = bad
            failed = ask()
            assert failed.status_code == 503 and "Ollama" in failed.json()["detail"]
        assert c.post("/api/assistant/chat", json={"messages": []}).status_code == 422
        assert c.post("/api/assistant/chat", json={"messages": [{"role": "assistant", "content": "Hi"}]}).status_code == 422
        assert c.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "x" * 1001}]}).status_code == 422


def test_every_page_the_assistant_can_open_exists_in_the_app():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "frontend" / "src" / "app"
    for name, path in assistant.PAGES.items():
        folder = root if path == "/" else root / path.strip("/")
        assert (folder / "page.tsx").is_file(), f"{name} -> {path} has no page"


def test_developer_endpoint_list_describes_the_api():
    with TestClient(app) as c:
        body = c.get("/api/developers/endpoints").json()
        assert body["count"] == len(body["endpoints"]) > 100
        batch = next(e for e in body["endpoints"] if e["path"] == "/api/movies/batch")
        assert batch["method"] == "POST" and batch["body"] == "json" and batch["group"] == "movies"
        document = next(e for e in body["endpoints"] if e["path"] == "/api/slides/document-brief")
        assert document["body"] == "multipart"
        assert any(e["path"] == "/api/recordings" for e in body["endpoints"])
        assert not any(e["path"].startswith("/api/developers") for e in body["endpoints"])
        assert c.get("/docs").status_code == 200 and c.get("/openapi.json").status_code == 200


def test_assistant_replaces_a_reply_that_is_only_a_keyword(model):
    with TestClient(app):
        c = _signed_in("assist_keyword")
        ask = lambda: c.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "credits?"}]}).json()["reply"]
        for junk in ("show_credits", "list_avatars", "ok", "Batch videos", "Just say 'show_credits' to see it."):
            model["reply"] = Reply({"reply": junk, "action": "show_credits", "page": ""})
            assert ask().startswith("Here is your balance. You have ")
        model["reply"] = Reply({"reply": "open_page", "action": "open_page", "page": "Brand systems"})
        out = c.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "brand"}]}).json()
        assert out["reply"] == "Opening Brand systems." and out["navigate_to"] == "/brand"
