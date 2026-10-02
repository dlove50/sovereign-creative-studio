"""Users can trash their own avatar videos; trashed videos leave the list and are restorable."""
import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import AvatarJob, User
from app.services import trash


@pytest.fixture(scope="module", autouse=True)
def _app_ready():
    with TestClient(app):
        yield


def _signup(username: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/signup", json={"username": username, "password": "trashpass1", "name": username}).status_code == 201
    return c


def _job_for(username: str) -> str:
    with SessionLocal() as db:
        uid = db.query(User).filter(User.username == username).one().id
        job = AvatarJob(user_id=uid, job_type="avatar_talking", status="completed", provider="test", credits_cost=0)
        db.add(job)
        db.commit()
        return job.id


def test_owner_trashes_avatar_video_and_admin_can_restore():
    c = _signup("trash_owner")
    job_id = _job_for("trash_owner")
    assert any(j["id"] == job_id for j in c.get("/api/avatar-jobs").json())

    assert c.delete(f"/api/avatar-jobs/{job_id}").status_code == 204
    assert all(j["id"] != job_id for j in c.get("/api/avatar-jobs").json())

    with SessionLocal() as db:
        assert any(i.entity_id == job_id for i in trash.list_trash(db))
        trash.restore(db, "avatar_video", job_id)
    assert any(j["id"] == job_id for j in c.get("/api/avatar-jobs").json())


def test_cannot_trash_someone_elses_video():
    _signup("trash_victim")
    other = _signup("trash_other")
    job_id = _job_for("trash_victim")
    assert other.delete(f"/api/avatar-jobs/{job_id}").status_code == 404
    assert other.delete("/api/videos/not-a-real-id").status_code == 404
