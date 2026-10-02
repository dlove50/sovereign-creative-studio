"""Avatar looks: grouping under a base avatar, ownership checks, deletion."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

PNG = b"\x89PNG\r\n\x1a\nfakeimage"


@pytest.fixture(scope="module", autouse=True)
def _app_ready():
    with TestClient(app):
        yield


def _client(username: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/signup", json={"username": username, "password": "lookspass1", "name": username})
    assert r.status_code == 201, r.text
    return c


def _photo(c, name="Base", **form):
    r = c.post("/api/avatars/photo", data={"name": name, **form}, files={"file": ("p.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    return r.json()


def test_look_joins_base_group_and_look_of_look_joins_same_base():
    c = _client("looks_group")
    base = _photo(c)
    assert base["group_id"] is None
    look = _photo(c, "Office", group_id=base["id"], look_label="Business suit in an office")
    assert look["group_id"] == base["id"] and look["look_label"] == "Business suit in an office"
    look_of_look = _photo(c, "Again", group_id=look["id"])
    assert look_of_look["group_id"] == base["id"]


def test_cannot_add_look_to_someone_elses_avatar():
    owner = _client("looks_owner")
    other = _client("looks_other")
    base = _photo(owner)
    r = other.post(
        "/api/avatars/photo", data={"name": "x", "group_id": base["id"]},
        files={"file": ("p.png", PNG, "image/png")},
    )
    assert r.status_code == 404


def test_deleting_base_removes_its_looks_but_deleting_a_look_keeps_base():
    c = _client("looks_delete")
    base = _photo(c)
    keep = _photo(c, "Keep", group_id=base["id"])
    drop = _photo(c, "Drop", group_id=base["id"])

    assert c.delete(f"/api/avatars/{drop['id']}").status_code == 204
    ids = {a["id"] for a in c.get("/api/avatars").json()}
    assert base["id"] in ids and keep["id"] in ids and drop["id"] not in ids

    assert c.delete(f"/api/avatars/{base['id']}").status_code == 204
    ids = {a["id"] for a in c.get("/api/avatars").json()}
    assert base["id"] not in ids and keep["id"] not in ids


def test_cannot_delete_someone_elses_avatar():
    owner = _client("looks_del_owner")
    other = _client("looks_del_other")
    base = _photo(owner)
    assert other.delete(f"/api/avatars/{base['id']}").status_code == 404
