"""Interactive videos: graph validation and the CRUD API."""
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
from app.services import interactive  # noqa: E402


def _node(node_id, choices=(), url="/storage/videos/a.mp4"):
    return {"id": node_id, "title": node_id, "video_url": url, "choices": [{"label": l, "next": n} for l, n in choices]}


def test_valid_graph_defaults_the_start_to_the_first_clip():
    nodes, start = interactive.clean_nodes([_node("a", [("Go", "b")]), _node("b")], None)
    assert start == "a" and nodes[0]["choices"] == [{"label": "Go", "next": "b"}]


@pytest.mark.parametrize("nodes,start,message", [
    ([_node("a"), _node("a")], None, "own id"),
    ([_node("a", [("Go", "zzz")])], None, "does not exist"),
    ([_node("a", [("  ", "a")])], None, "no label"),
    ([_node("a", url="https://evil.example/x.mp4")], None, "/storage/"),
    ([_node("a")], "nope", "starting clip"),
])
def test_bad_graphs_are_rejected_with_plain_messages(nodes, start, message):
    with pytest.raises(ValueError, match=message):
        interactive.clean_nodes(nodes, start)


def test_choices_are_capped_and_loops_are_allowed():
    many = [("c%d" % i, "a") for i in range(9)]
    nodes, _ = interactive.clean_nodes([_node("a", many)], "a")
    assert len(nodes[0]["choices"]) == interactive.MAX_CHOICES


def test_api_round_trip_and_ownership():
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "ia_user", "password": "interactive1", "name": "I"}).status_code == 201
        body = {"title": "Pick a path", "nodes": [_node("a", [("Left", "b"), ("Right", "c")]), _node("b"), _node("c")]}
        made = c.post("/api/interactive", json=body)
        assert made.status_code == 201, made.text
        item = made.json()
        assert item["start_node_id"] == "a" and len(item["nodes"]) == 3
        assert c.get(f"/api/interactive/{item['id']}").json()["title"] == "Pick a path"
        bad = c.put(f"/api/interactive/{item['id']}", json={"nodes": [_node("a", [("Go", "ghost")])]})
        assert bad.status_code == 422
        assert len(c.get(f"/api/interactive/{item['id']}").json()["nodes"]) == 3  # failed save changed nothing
        assert c.get("/api/interactive/clips").status_code == 200
        assert c.delete(f"/api/interactive/{item['id']}").status_code == 204
        assert c.get(f"/api/interactive/{item['id']}").status_code == 404
        assert c.get("/api/interactive").json() == []
