"""Delete controls: generated images, brand systems (projects) and batch drafts can be removed, safely."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Generation, User  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\nfakeimage"


@pytest.fixture(scope="module", autouse=True)
def _app_ready():
    with TestClient(app):
        yield


def _client(name):
    c = TestClient(app)
    assert c.post("/api/auth/signup", json={"username": name, "password": "deletepass1", "name": name}).status_code == 201
    return c


def _image(username, status="completed", name="made.png", project_id=None):
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    (config.STORAGE_DIR / name).write_bytes(PNG)
    with SessionLocal() as db:
        owner = db.query(User).filter(User.username == username).one()
        row = Generation(user_id=owner.id, prompt="a test picture", status=status, file_url=f"/storage/{name}", project_id=project_id)
        db.add(row)
        db.commit()
        return row.id


def test_a_generated_image_can_be_deleted_into_the_recoverable_trash():
    c = _client("del_image")
    keep, gone = _image("del_image", name="keep.png"), _image("del_image", name="gone.png")
    assert {g["id"] for g in c.get("/api/generations").json()} >= {keep, gone}
    assert c.delete(f"/api/generations/{gone}").status_code == 204
    listed = {g["id"] for g in c.get("/api/generations").json()}
    assert gone not in listed and keep in listed
    assert not (config.STORAGE_DIR / "gone.png").exists() and (config.STORAGE_DIR / "trash" / "gone.png").read_bytes() == PNG  # kept, not destroyed
    assert (config.STORAGE_DIR / "keep.png").exists()
    assert c.delete(f"/api/generations/{gone}").status_code == 404  # already gone


def test_images_still_being_made_and_other_peoples_images_cannot_be_deleted():
    owner, stranger = _client("del_owner"), _client("del_stranger")
    busy = _image("del_owner", status="running", name="busy.png")
    mine = _image("del_owner", name="mine.png")
    assert owner.delete(f"/api/generations/{busy}").status_code == 409
    assert stranger.delete(f"/api/generations/{mine}").status_code == 404
    assert stranger.delete("/api/generations/does-not-exist").status_code == 404
    assert (config.STORAGE_DIR / "mine.png").exists() and mine in {g["id"] for g in owner.get("/api/generations").json()}


def test_an_empty_brand_system_can_be_deleted_but_one_with_content_is_protected():
    c = _client("del_brand")
    empty = c.post("/api/projects", json={"name": "Empty brand"}).json()["id"]
    used = c.post("/api/projects", json={"name": "Brand in use"}).json()["id"]
    folder = config.STORAGE_DIR / "brand" / empty
    folder.mkdir(parents=True)
    (folder / "logo.png").write_bytes(PNG)
    _image("del_brand", name="inbrand.png", project_id=used)

    refused = c.delete(f"/api/projects/{used}")
    assert refused.status_code == 409 and "Still attached: generations (1)" in refused.json()["detail"]
    assert used in {p["id"] for p in c.get("/api/projects").json()}

    assert c.delete(f"/api/projects/{empty}").status_code == 204
    assert empty not in {p["id"] for p in c.get("/api/projects").json()} and not folder.exists()
    assert c.get(f"/api/projects/{empty}").status_code == 404
    assert _client("del_brand_stranger").delete(f"/api/projects/{used}").status_code == 404


def test_batch_drafts_can_be_deleted_but_a_rendering_video_cannot():
    c = _client("del_movies")
    avatar = c.post("/api/avatars/photo", data={"name": "P"}, files={"file": ("p.png", PNG, "image/png")}).json()["id"]
    made = c.post("/api/movies/batch", json={"avatar_id": avatar, "rows": [{"script": "One."}, {"script": "Two."}]}).json()
    assert len(made) == 2
    assert c.delete(f"/api/movies/{made[0]['id']}").status_code == 204
    left = {m["id"] for m in c.get("/api/movies").json()}
    assert made[0]["id"] not in left and made[1]["id"] in left
    from app.models import Movie
    with SessionLocal() as db:
        db.get(Movie, made[1]["id"]).status = "rendering"
        db.commit()
    assert c.delete(f"/api/movies/{made[1]['id']}").status_code == 409
