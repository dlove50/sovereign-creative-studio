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
        from app.database import SessionLocal
        from app.models import User, Project, VideoGeneration
        from sqlalchemy import select
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.username == "ia_user"))
            project = Project(user_id=user.id, name="Interactive clips")
            db.add(project)
            db.flush()
            db.add(VideoGeneration(user_id=user.id, project_id=project.id, prompt="clip", source_image_url="",
                                   motion_preset="static", duration_seconds=5, status="completed", result_url="/storage/videos/a.mp4"))
            db.commit()
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


def test_training_feedback_and_answers_roundtrip():
    first = _node("question", [("Try again", "question"), ("Continue", "end")], url="")
    first["question"] = "Which action is correct?"
    first["choices"][0].update(is_correct=False, feedback="Review the first step.")
    first["choices"][1].update(is_correct=True, feedback="Correct. Continue.")
    nodes, _ = interactive.clean_nodes([first, _node("end", url="")], None)
    assert nodes[0]["question"] == first["question"]
    assert nodes[0]["choices"][0]["is_correct"] is False
    assert nodes[0]["choices"][1]["feedback"] == "Correct. Continue."


@pytest.mark.parametrize("choices", [[], [{"label":"Wrong", "next":"a", "is_correct":False}], [{"label":"Ungraded", "next":"a"}]])
def test_question_requires_valid_grading(choices):
    with pytest.raises(ValueError, match="graded choices"):
        interactive.clean_nodes([{"id":"a", "question":"Choose", "choices":choices}], None)


def test_clip_ownership_and_traversal(stored_api):
    client, _, _ = stored_api
    assert client.post('/api/interactive',json={'nodes':[_node('a',url='/storage/foreign.mp4')]}).status_code == 404
    assert client.post('/api/interactive',json={'nodes':[_node('a',url='/storage/../foreign.mp4')]}).status_code == 400
    assert client.post('/api/interactive',json={'nodes':[_node('a',url='')]}).status_code == 201


def test_training_instructions_survive_save_and_reload(stored_api):
    client, _, _ = stored_api
    node = {**_node('intro', url=''), 'body': 'Review the workplace reporting procedure.'}
    response = client.post('/api/interactive', json={'nodes': [node]})
    assert response.status_code == 201
    saved = client.get('/api/interactive/' + response.json()['id']).json()
    assert saved['nodes'][0]['body'] == node['body']
    node['body'] = 'x' * 4001
    assert client.post('/api/interactive', json={'nodes': [node]}).status_code == 422


from test_cinematic_plan_storage import stored_api


def test_frontend_training_example_roundtrip(stored_api):
    import json
    from pathlib import Path
    client, _, _ = stored_api
    source = Path(__file__).resolve().parents[2] / 'frontend/src/lib/training-example.json'
    example = json.loads(source.read_text(encoding='utf-8-sig'))
    response = client.post('/api/interactive', json=example)
    assert response.status_code == 201, response.text
    saved = client.get('/api/interactive/' + response.json()['id']).json()
    by_id = {node['id']: node for node in saved['nodes']}
    assert len(by_id) == 5
    for original in example['nodes']:
        assert by_id[original['id']].get('body', '') == original.get('body', '')
        assert by_id[original['id']]['choices'] == original['choices']
    question = by_id['question']
    wrong = next(c for c in question['choices'] if c['is_correct'] is False)
    assert by_id[wrong['next']]['choices'][0]['next'] == 'question'
    assert not by_id['end']['choices']
