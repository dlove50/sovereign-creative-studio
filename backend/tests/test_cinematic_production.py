"""Tests for CinematicProduction model, API routes, and lossless assembly service."""
from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient

from app import config
from app.database import SessionLocal
from app.main import app
from app.models import CinematicPlan, CinematicProduction, VideoGeneration, User
from app.services import cinematic_assembly


@pytest.fixture(scope="module", autouse=True)
def _app_ready():
    with TestClient(app):
        yield


def _client(username: str) -> TestClient:
    c = TestClient(app)
    res = c.post("/api/auth/signup", json={"username": username, "password": "cinematicpass1", "name": username})
    assert res.status_code == 201
    return c


@pytest.fixture
def plan_data():
    return {
        "title": "Courtyard Sparring",
        "synopsis": "Martial artists bow and spar.",
        "characters": [{"id": "c1", "name": "Kenji", "description": "Blue gi"}],
        "locations": [{"id": "l1", "name": "Courtyard", "description": "Stone patio"}],
        "shots": [
            {
                "id": "shot_1",
                "duration_seconds": 5,
                "location_id": "l1",
                "character_ids": ["c1"],
                "description": "Stance preparation",
                "camera": "Eye-level wide",
                "dialogue": [],
                "narration": "",
                "transition": "Cut",
                "image_prompt": "Kenji in blue gi",
                "video_prompt": "Kenji steps into stance"
            },
            {
                "id": "shot_2",
                "duration_seconds": 5,
                "location_id": "l1",
                "character_ids": ["c1"],
                "description": "Bow",
                "camera": "Eye-level medium",
                "dialogue": [],
                "narration": "",
                "transition": "Fade Out",
                "image_prompt": "Kenji bowing",
                "video_prompt": "Kenji bows respectfully"
            }
        ],
        "model": "qwen3.8:27b"
    }


def _create_saved_plan(client: TestClient, plan_data: dict) -> dict:
    res = client.post("/api/video-agent/plans", json={
        "prompt": "Martial artists bowing and sparring",
        "seconds": 10,
        "plan": plan_data
    })
    assert res.status_code == 201
    return res.json()


def _create_completed_video(client: TestClient, username: str, duration: int = 5) -> str:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one()
        from app.models import Project
        proj = db.query(Project).filter(Project.user_id == user.id).first()
        if not proj:
            proj = Project(user_id=user.id, name="Test Project")
            db.add(proj)
            db.commit()
            db.refresh(proj)
        
        video_id = f"test_vid_{username}_{duration}_{Path(config.STORAGE_DIR).name}"
        # Create a mock video file in storage/videos
        vids_dir = Path(config.STORAGE_DIR) / "videos"
        vids_dir.mkdir(parents=True, exist_ok=True)
        vid_file = vids_dir / f"{video_id}.mp4"
        vid_file.write_bytes(b"dummy mp4 content for testing")
        
        row = VideoGeneration(
            id=video_id,
            user_id=user.id,
            project_id=proj.id,
            source_image_url="/storage/images/dummy.png",
            mode="image_to_video",
            provider="local_minimax_h3",
            prompt="Sparring shot",
            motion_preset="subtle",
            duration_seconds=duration,
            status="completed",
            result_url=f"/storage/videos/{video_id}.mp4"
        )
        db.merge(row)
        db.commit()
    return video_id


def test_production_lifecycle_get_attach_assemble(monkeypatch, plan_data):
    c = _client("cinematic_user1")
    plan = _create_saved_plan(c, plan_data)
    plan_id = plan["id"]
    revision = plan["revision"]

    # 1. Get initial production draft
    prod_res = c.get(f"/api/video-agent/plans/{plan_id}/production")
    assert prod_res.status_code == 200
    prod = prod_res.json()
    assert prod["status"] == "draft"
    assert len(prod["shots"]) == 2
    assert all(s["video_id"] is None for s in prod["shots"])

    # 2. Attach completed clips to shot 1 and shot 2
    vid1 = _create_completed_video(c, "cinematic_user1", 5)
    vid2 = _create_completed_video(c, "cinematic_user1", 5)

    att1 = c.put(f"/api/video-agent/plans/{plan_id}/shots/shot_1", json={
        "revision": revision,
        "video_id": vid1
    })
    assert att1.status_code == 200
    assert att1.json()["shots"][0]["video_id"] == vid1

    # Attempting to assemble before all shots are linked should fail with 409
    assemble_early = c.post(f"/api/video-agent/plans/{plan_id}/assemble", json={
        "revision": revision
    })
    assert assemble_early.status_code == 409
    assert "every shot" in assemble_early.json()["detail"]

    # Link shot 2
    att2 = c.put(f"/api/video-agent/plans/{plan_id}/shots/shot_2", json={
        "revision": revision,
        "video_id": vid2
    })
    assert att2.status_code == 200
    assert att2.json()["shots"][1]["video_id"] == vid2

    # Mock assemble_clips to succeed
    def mock_assemble(clips, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"assembled mp4 dummy")

    monkeypatch.setattr("app.routers.video_agent.assemble_clips", mock_assemble)

    # 3. Assemble
    assembled = c.post(f"/api/video-agent/plans/{plan_id}/assemble", json={
        "revision": revision
    })
    assert assembled.status_code == 200
    body = assembled.json()
    assert body["status"] == "completed"
    assert body["result_url"] is not None
    assert body["result_url"].startswith("/storage/videos/cinematic-")


def test_production_revision_and_ownership_isolation(plan_data):
    owner = _client("cinematic_owner")
    stranger = _client("cinematic_stranger")
    
    plan = _create_saved_plan(owner, plan_data)
    plan_id = plan["id"]

    # Stranger cannot view production
    assert stranger.get(f"/api/video-agent/plans/{plan_id}/production").status_code == 404

    # Stranger cannot link shots
    assert stranger.put(f"/api/video-agent/plans/{plan_id}/shots/shot_1", json={
        "revision": 1,
        "video_id": "fake"
    }).status_code == 404

    # Stale revision is rejected
    assert owner.put(f"/api/video-agent/plans/{plan_id}/shots/shot_1", json={
        "revision": 999,
        "video_id": "fake"
    }).status_code == 409


def test_cinematic_assembly_validation(tmp_path):
    # Empty clips list should raise ValueError
    with pytest.raises(ValueError, match="needs separate input clips"):
        cinematic_assembly.assemble_clips([], tmp_path / "out.mp4")

    # Destination in clips should raise ValueError
    clip1 = tmp_path / "c1.mp4"
    clip1.write_bytes(b"c1")
    with pytest.raises(ValueError, match="needs separate input clips"):
        cinematic_assembly.assemble_clips([clip1], clip1)
