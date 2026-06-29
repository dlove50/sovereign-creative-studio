"""Image-to-video foundation tests (mock generator)."""
import os
import tempfile
import time

_TMP = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{os.path.join(_TMP, 'test.db')}")
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "storage"))
os.environ.setdefault("GENERATOR_BACKEND", "mock")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import videos as videos_router  # noqa: E402
import app.video_generators as video_generators_module  # noqa: E402
from app.video_generators.mock import build_video_html  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _mock_video_backend(monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "mock")
    monkeypatch.setattr(video_generators_module, "VIDEO_BACKEND", "mock")
    # Video generations now cost credits; keep the shared test user funded so
    # these functional video tests are not starved by the per-video charge.
    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        for user in db.query(User).all():
            user.credits = 100000
        db.commit()


def _wait(client, path, status, timeout=5.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = client.get(path).json()
        if latest["status"] == status:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"{path} did not reach {status}: {latest}")


def _completed_scene(client):
    project_id = client.post(
        "/api/projects", json={"name": "Video", "description": None}
    ).json()["id"]
    asset = client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": ("thing.png", b"bytes", "image/png")},
    ).json()
    scene = client.post(
        "/api/product-scenes",
        json={
            "project_id": project_id,
            "asset_id": asset["id"],
            "prompt": "thing on marble",
            "preset": "studio",
        },
    ).json()
    completed = _wait(client, f"/api/product-scenes/{scene['id']}", "completed")
    return project_id, completed


# --- mock unit ---------------------------------------------------------------
@pytest.mark.parametrize(
    "preset",
    [
        "slow_zoom",
        "orbit",
        "handheld",
        "product_reveal",
        "product_motion",
        "cinematic_push",
        "runway_walk",
        "parallax",
        "dolly_in",
        "subtle_breathing",
    ],
)
def test_build_video_html_for_each_preset(preset):
    html = build_video_html(
        source_image_url="/storage/product-scenes/x.svg",
        prompt="dramatic reveal",
        motion_preset=preset,
        duration_seconds=6,
    )
    assert "@keyframes motion" in html
    assert "/storage/product-scenes/x.svg" in html
    assert "6s" in html


# --- API ---------------------------------------------------------------------
def test_create_video_from_scene_completes(client):
    project_id, scene = _completed_scene(client)
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "product_scene_id": scene["id"],
            "prompt": "slow push in",
            "motion_preset": "slow_zoom",
            "duration_seconds": 6,
            "quality_preset": "image_to_video_best",
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["status"] == "queued"
    assert created["quality_preset"] == "image_to_video_best"
    # Source image is taken from the completed scene.
    assert created["source_image_url"] == scene["result_url"]

    done = _wait(client, f"/api/videos/{created['id']}", "completed")
    assert done["result_url"].endswith(".html")

    listed = client.get("/api/videos").json()
    assert any(v["id"] == created["id"] for v in listed)


def test_create_video_with_explicit_source_url(client):
    project_id = client.post(
        "/api/projects", json={"name": "V2", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "source_image_url": "/storage/product-scenes/abc.svg",
            "prompt": "orbit around",
            "motion_preset": "orbit",
            "duration_seconds": 4,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["source_image_url"] == "/storage/product-scenes/abc.svg"


def test_video_requires_a_source(client):
    project_id = client.post(
        "/api/projects", json={"name": "V3", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "prompt": "no source",
            "motion_preset": "handheld",
            "duration_seconds": 5,
        },
    )
    assert resp.status_code == 400


def test_comfyui_rejects_video_extension_when_not_ready(client, monkeypatch):
    # Video Extension is wired, but the readiness gate must reject when its
    # ComfyUI workflow/nodes/model are not actually available.
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(
        videos_router,
        "_video_extension_ready",
        lambda: (False, "Video Extension workflow missing"),
    )
    project_id = client.post(
        "/api/projects", json={"name": "Comfy mode guard", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "source_image_url": "/storage/videos/source.mp4",
            "prompt": "extend this clip",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "video_extension",
        },
    )
    assert resp.status_code == 409
    assert "Video Extension is not ready" in resp.json()["detail"]


def test_comfyui_allows_text_to_video_when_workflow_ready(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(videos_router, "_text_to_video_ready", lambda: (True, None))
    project_id = client.post(
        "/api/projects", json={"name": "Comfy text video", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "prompt": "a premium product rotating under studio light",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "text_to_video",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mode"] == "text_to_video"
    assert body["source_image_url"] == ""


def test_comfyui_rejects_text_to_video_when_not_ready(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(
        videos_router,
        "_text_to_video_ready",
        lambda: (False, "Text -> Video workflow missing"),
    )
    project_id = client.post(
        "/api/projects", json={"name": "Comfy text blocked", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "prompt": "a premium product rotating under studio light",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "text_to_video",
        },
    )
    assert resp.status_code == 409
    assert "Text -> Video is not ready" in resp.json()["detail"]


def test_comfyui_modes_marks_text_to_video_ready(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(videos_router, "_text_to_video_ready", lambda: (True, None))
    monkeypatch.setattr(videos_router, "_video_to_video_ready", lambda: (False, "missing"))
    monkeypatch.setattr(videos_router, "_video_upscale_ready", lambda: (False, "missing"))

    modes = {item["id"]: item for item in client.get("/api/videos/modes").json()}
    assert modes["image_to_video"]["available"] is True
    assert modes["text_to_video"]["available"] is True
    assert modes["text_to_video"]["backend"] == "ComfyUI/LTX"
    assert modes["video_upscale"]["available"] is False
    assert modes["video_upscale"]["note"] == "missing"


def test_comfyui_modes_marks_text_to_video_unavailable(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(
        videos_router,
        "_text_to_video_ready",
        lambda: (False, "Missing ComfyUI nodes: SaveVideo"),
    )
    monkeypatch.setattr(videos_router, "_video_to_video_ready", lambda: (False, "missing"))
    monkeypatch.setattr(videos_router, "_video_upscale_ready", lambda: (False, "missing"))

    modes = {item["id"]: item for item in client.get("/api/videos/modes").json()}
    assert modes["text_to_video"]["available"] is False
    assert modes["text_to_video"]["note"] == "Missing ComfyUI nodes: SaveVideo"


def test_comfyui_allows_video_upscale_when_workflow_ready(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(videos_router, "_video_upscale_ready", lambda: (True, None))
    project_id = client.post(
        "/api/projects", json={"name": "Comfy upscale video", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "source_image_url": "/storage/videos/source.mp4",
            "prompt": "upscale existing video",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "video_upscale",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mode"] == "video_upscale"
    assert body["source_image_url"] == "/storage/videos/source.mp4"


def test_comfyui_rejects_video_upscale_when_not_ready(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(
        videos_router,
        "_video_upscale_ready",
        lambda: (False, "LTX spatial upscaler not listed in ComfyUI"),
    )
    project_id = client.post(
        "/api/projects", json={"name": "Comfy upscale blocked", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "source_image_url": "/storage/videos/source.mp4",
            "prompt": "upscale existing video",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "video_upscale",
        },
    )
    assert resp.status_code == 409
    assert "Video Upscale is not ready" in resp.json()["detail"]


def test_comfyui_modes_marks_video_upscale_ready(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(videos_router, "_text_to_video_ready", lambda: (True, None))
    monkeypatch.setattr(videos_router, "_video_to_video_ready", lambda: (False, "missing"))
    monkeypatch.setattr(videos_router, "_video_upscale_ready", lambda: (True, None))

    modes = {item["id"]: item for item in client.get("/api/videos/modes").json()}
    assert modes["video_upscale"]["available"] is True
    assert modes["video_upscale"]["backend"] == "ComfyUI/LTX"
    assert modes["video_to_video"]["available"] is False


def test_comfyui_modes_marks_video_upscale_unavailable(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(videos_router, "_text_to_video_ready", lambda: (True, None))
    monkeypatch.setattr(videos_router, "_video_to_video_ready", lambda: (False, "missing"))
    monkeypatch.setattr(
        videos_router,
        "_video_upscale_ready",
        lambda: (False, "Missing ComfyUI nodes: LoadVideo"),
    )

    modes = {item["id"]: item for item in client.get("/api/videos/modes").json()}
    assert modes["video_upscale"]["available"] is False
    assert modes["video_upscale"]["note"] == "Missing ComfyUI nodes: LoadVideo"


def test_comfyui_allows_video_to_video_when_workflow_ready(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(videos_router, "_video_to_video_ready", lambda: (True, None))
    project_id = client.post(
        "/api/projects", json={"name": "Comfy v2v video", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "source_image_url": "/storage/videos/source.mp4",
            "prompt": "restyle existing video",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "video_to_video",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["mode"] == "video_to_video"
    assert body["source_image_url"] == "/storage/videos/source.mp4"


def test_comfyui_rejects_video_to_video_when_not_ready(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(
        videos_router,
        "_video_to_video_ready",
        lambda: (False, "Missing ComfyUI nodes: LoadVideo"),
    )
    project_id = client.post(
        "/api/projects", json={"name": "Comfy v2v blocked", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "source_image_url": "/storage/videos/source.mp4",
            "prompt": "restyle existing video",
            "motion_preset": "slow_zoom",
            "duration_seconds": 3,
            "mode": "video_to_video",
        },
    )
    assert resp.status_code == 409
    assert "Video -> Video is not ready" in resp.json()["detail"]


def test_comfyui_modes_marks_video_to_video_ready(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(videos_router, "_text_to_video_ready", lambda: (True, None))
    monkeypatch.setattr(videos_router, "_video_to_video_ready", lambda: (True, None))
    monkeypatch.setattr(videos_router, "_video_upscale_ready", lambda: (True, None))
    monkeypatch.setattr(videos_router, "_video_extension_ready", lambda: (True, None))

    modes = {item["id"]: item for item in client.get("/api/videos/modes").json()}
    assert modes["video_to_video"]["available"] is True
    assert modes["video_to_video"]["backend"] == "ComfyUI/LTX"
    assert modes["video_extension"]["available"] is True
    assert modes["video_extension"]["note"] is None


def test_comfyui_modes_marks_video_to_video_unavailable(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(videos_router, "_text_to_video_ready", lambda: (True, None))
    monkeypatch.setattr(
        videos_router,
        "_video_to_video_ready",
        lambda: (False, "LTX text encoder not listed in ComfyUI"),
    )
    monkeypatch.setattr(videos_router, "_video_upscale_ready", lambda: (True, None))

    modes = {item["id"]: item for item in client.get("/api/videos/modes").json()}
    assert modes["video_to_video"]["available"] is False
    assert modes["video_to_video"]["note"] == "LTX text encoder not listed in ComfyUI"


def test_comfyui_modes_marks_video_extension_unavailable(client, monkeypatch):
    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(videos_router, "_text_to_video_ready", lambda: (True, None))
    monkeypatch.setattr(videos_router, "_video_to_video_ready", lambda: (True, None))
    monkeypatch.setattr(videos_router, "_video_upscale_ready", lambda: (True, None))
    monkeypatch.setattr(
        videos_router,
        "_video_extension_ready",
        lambda: (False, "Missing ComfyUI nodes: LTXVAddGuide"),
    )

    modes = {item["id"]: item for item in client.get("/api/videos/modes").json()}
    assert modes["video_extension"]["available"] is False
    assert modes["video_extension"]["note"] == "Missing ComfyUI nodes: LTXVAddGuide"


def test_invalid_motion_preset_rejected(client):
    project_id = client.post(
        "/api/projects", json={"name": "V4", "description": None}
    ).json()["id"]
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "source_image_url": "/storage/x.svg",
            "prompt": "x",
            "motion_preset": "teleport",
            "duration_seconds": 5,
        },
    )
    assert resp.status_code == 422


def test_video_to_missing_project_is_404(client):
    resp = client.post(
        "/api/videos",
        json={
            "project_id": "nope",
            "source_image_url": "/storage/x.svg",
            "prompt": "x",
            "motion_preset": "orbit",
            "duration_seconds": 5,
        },
    )
    assert resp.status_code == 404


# --- creative brief integration ----------------------------------------------
def test_video_with_brief_appends_context(client):
    project_id, scene = _completed_scene(client)
    brief = client.post(
        f"/api/projects/{project_id}/briefs",
        json={"title": "Motion brief", "creative_direction": "Slow cinematic push"},
    ).json()

    created = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "product_scene_id": scene["id"],
            "prompt": "gentle motion",
            "motion_preset": "slow_zoom",
            "duration_seconds": 5,
            "brief_id": brief["id"],
        },
    )
    assert created.status_code == 201
    stored_prompt = created.json()["prompt"]
    assert "Creative brief:" in stored_prompt
    assert "Slow cinematic push" in stored_prompt


def test_video_with_invalid_brief_is_404(client):
    project_id, scene = _completed_scene(client)
    resp = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "product_scene_id": scene["id"],
            "prompt": "x",
            "motion_preset": "orbit",
            "duration_seconds": 4,
            "brief_id": "does-not-exist",
        },
    )
    assert resp.status_code == 404


# --- export ------------------------------------------------------------------
def test_export_completed_video(client):
    project_id, scene = _completed_scene(client)
    created = client.post(
        "/api/videos",
        json={
            "project_id": project_id,
            "product_scene_id": scene["id"],
            "prompt": "reveal",
            "motion_preset": "product_reveal",
            "duration_seconds": 5,
        },
    ).json()
    _wait(client, f"/api/videos/{created['id']}", "completed")

    resp = client.get(f"/api/exports/video/{created['id']}")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert resp.content


def test_export_unknown_video_is_404(client):
    assert client.get("/api/exports/video/nope").status_code == 404
