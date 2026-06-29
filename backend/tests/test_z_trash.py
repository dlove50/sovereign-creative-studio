"""Selective asset trash: recoverable soft delete with protection for originals
and referenced assets."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import config
from app.database import SessionLocal
from app.main import app
from app.models import (
    ProductAsset,
    ProductSceneGeneration,
    Project,
    Shot,
    Storyboard,
    User,
    VideoGeneration,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _owner_id():
    with SessionLocal() as db:
        return db.scalars(select(User).order_by(User.created_at)).first().id


def _project(uid):
    with SessionLocal() as db:
        p = Project(user_id=uid, name="trash-proj", description=None)
        db.add(p)
        db.commit()
        return p.id


def _write(rel: str) -> str:
    path = config.STORAGE_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"FAKE-MEDIA")
    return f"/storage/{rel}"


def _video(uid, pid):
    with SessionLocal() as db:
        v = VideoGeneration(
            user_id=uid, project_id=pid, source_image_url="", mode="text_to_video",
            prompt="trash clip", motion_preset="slow_zoom", duration_seconds=3, status="completed",
        )
        db.add(v); db.commit()
        v.result_url = _write(f"videos/{v.id}.mp4")
        db.commit()
        return v.id


def _scene(uid, pid, asset_id):
    with SessionLocal() as db:
        s = ProductSceneGeneration(
            user_id=uid, project_id=pid, asset_id=asset_id, prompt="trash scene",
            preset="studio", status="completed",
        )
        db.add(s); db.commit()
        s.result_url = _write(f"product-scenes/{s.id}.png")
        db.commit()
        return s.id


def _upload(uid, pid):
    with SessionLocal() as db:
        a = ProductAsset(user_id=uid, project_id=pid, filename="orig.png", original_url="x", status="uploaded")
        db.add(a); db.commit()
        a.original_url = _write(f"uploads/{a.id}.png")
        db.commit()
        return a.id


def test_video_moved_to_trash_file_preserved(client):
    uid = _owner_id(); pid = _project(uid)
    vid = _video(uid, pid)
    live = config.STORAGE_DIR / "videos" / f"{vid}.mp4"
    assert live.is_file()
    r = client.post("/api/admin/trash", json={"entity_type": "video", "entity_id": vid}).json()
    assert r["trashed"] is True
    # physical file moved to trash (recoverable), not destroyed
    assert not live.is_file()
    assert (config.STORAGE_DIR / "trash" / "videos" / f"{vid}.mp4").is_file()
    # hidden from videos list and library
    assert all(v["id"] != vid for v in client.get("/api/videos").json())
    assert all(it["id"] != f"video:{vid}" for it in client.get("/api/library").json())


def test_scene_moved_to_trash(client):
    uid = _owner_id(); pid = _project(uid)
    aid = _upload(uid, pid)
    sid = _scene(uid, pid, aid)
    r = client.post("/api/admin/trash", json={"entity_type": "scene", "entity_id": sid}).json()
    assert r["trashed"] is True
    assert (config.STORAGE_DIR / "trash" / "product-scenes" / f"{sid}.png").is_file()
    assert all(s["id"] != sid for s in client.get("/api/product-scenes").json())
    assert all(it["id"] != f"scene:{sid}" for it in client.get("/api/library").json())


def test_referenced_scene_protected_then_forced(client):
    uid = _owner_id(); pid = _project(uid)
    aid = _upload(uid, pid)
    sid = _scene(uid, pid, aid)
    with SessionLocal() as db:
        board = Storyboard(user_id=uid, project_id=pid, title="b", status="draft")
        db.add(board); db.commit()
        db.add(Shot(user_id=uid, storyboard_id=board.id, shot_number=1, duration_seconds=5, product_scene_id=sid))
        db.commit()
    blocked = client.post("/api/admin/trash", json={"entity_type": "scene", "entity_id": sid})
    assert blocked.status_code == 409 and "referenced" in blocked.json()["detail"].lower()
    forced = client.post(
        "/api/admin/trash",
        json={"entity_type": "scene", "entity_id": sid, "force_referenced": True},
    )
    assert forced.status_code == 200 and forced.json()["trashed"] is True


def test_original_upload_protected_then_forced(client):
    uid = _owner_id(); pid = _project(uid)
    aid = _upload(uid, pid)
    blocked = client.post("/api/admin/trash", json={"entity_type": "upload", "entity_id": aid})
    assert blocked.status_code == 409 and "original" in blocked.json()["detail"].lower()
    forced = client.post(
        "/api/admin/trash",
        json={"entity_type": "upload", "entity_id": aid, "force_original": True},
    )
    assert forced.status_code == 200 and forced.json()["trashed"] is True
    assert (config.STORAGE_DIR / "trash" / "uploads" / f"{aid}.png").is_file()


def test_trash_listed_and_restorable(client):
    uid = _owner_id(); pid = _project(uid)
    vid = _video(uid, pid)
    client.post("/api/admin/trash", json={"entity_type": "video", "entity_id": vid})
    listed = client.get("/api/admin/trash").json()
    assert any(t["entity_id"] == vid and t["entity_type"] == "video" for t in listed)
    # restore brings it back to normal listings and moves the file back
    client.post("/api/admin/trash/restore", json={"entity_type": "video", "entity_id": vid})
    assert (config.STORAGE_DIR / "videos" / f"{vid}.mp4").is_file()
    assert any(v["id"] == vid for v in client.get("/api/videos").json())
