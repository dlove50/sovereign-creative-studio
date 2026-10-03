"""MiniMax H3 provider: workflow graph, frame grid, readiness, and routing."""
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
from app.main import app  # noqa: E402
from app.routers import videos as videos_router  # noqa: E402
from app.video_generators import MiniMaxH3VideoGenerator, get_video_generator  # noqa: E402
from app.video_generators.minimax_h3 import (  # noqa: E402
    build_h3_workflow, h3_length_frames, h3_size, h3_size_for_aspect,
)


@pytest.mark.parametrize("seconds,frames", [(1, 56), (2, 56), (5, 124), (10, 243), (60, 362)])
def test_length_snaps_to_17k_plus_5_and_clamps_to_trained_range(seconds, frames):
    assert h3_length_frames(seconds) == frames
    assert frames % 17 == 5


def test_size_follows_orientation_in_multiples_of_32():
    assert h3_size(portrait=False) == (config.H3_LONG_SIDE, config.H3_SHORT_SIDE)
    assert h3_size(portrait=True) == (config.H3_SHORT_SIDE, config.H3_LONG_SIDE)
    assert all(v % 32 == 0 for v in (*h3_size(False), *h3_size(True)))


@pytest.mark.parametrize("aspect,expected", [(1.0, (640, 640)), (16 / 9, (832, 480)), (9 / 16, (480, 832)), (4 / 3, (736, 544))])
def test_output_keeps_the_source_aspect_ratio_instead_of_stretching_to_16_9(aspect, expected):
    width, height = h3_size_for_aspect(aspect)
    assert (width, height) == expected
    assert width % 32 == 0 and height % 32 == 0
    assert abs(width / height - aspect) / aspect < 0.1  # within snapping error


def test_image_to_video_graph_has_first_frame_turbo_and_audio():
    wf = build_h3_workflow(prompt="a dog runs", width=832, height=480, length=124, image_name="in.png", turbo=True, seed=7)
    cond = wf["7"]["inputs"]
    assert wf["7"]["class_type"] == "MiniMaxH3ImageToVideo"
    assert cond["first_frame"] == ["5", 0] and wf["5"]["inputs"]["image"] == "in.png"
    assert cond["prompt"] == "a dog runs" and cond["length"] == 124
    # turbo LoRA feeds both the guider and the scheduler, with 4 steps
    assert wf["9"]["inputs"]["model"] == ["6", 0] and wf["11"]["inputs"]["model"] == ["6", 0]
    assert wf["11"]["inputs"]["steps"] == config.H3_TURBO_STEPS
    assert wf["8"]["inputs"]["noise_seed"] == 7
    assert wf["15"]["inputs"] == {"images": ["13", 0], "audio": ["14", 0], "fps": 24}
    assert wf["16"]["class_type"] == "SaveVideo"


def test_text_to_video_graph_has_no_image_and_full_quality_skips_lora():
    wf = build_h3_workflow(prompt="rain", width=480, height=832, length=56, image_name=None, turbo=False)
    assert "5" not in wf and "first_frame" not in wf["7"]["inputs"]
    assert "6" not in wf and wf["9"]["inputs"]["model"] == ["1", 0]
    assert wf["11"]["inputs"]["steps"] == config.H3_FULL_STEPS


def test_every_node_reference_points_at_an_existing_node():
    wf = build_h3_workflow(prompt="x", width=832, height=480, length=56, image_name="a.png")
    for node_id, node in wf.items():
        for value in node["inputs"].values():
            if isinstance(value, list):
                assert value[0] in wf, f"node {node_id} references missing node {value[0]}"


def test_factory_returns_h3_generator_only_for_h3_on_comfyui(monkeypatch):
    monkeypatch.setattr("app.video_generators.VIDEO_BACKEND", "comfyui")
    assert isinstance(get_video_generator("local_h3"), MiniMaxH3VideoGenerator)
    assert not isinstance(get_video_generator("local_ltx"), MiniMaxH3VideoGenerator)


def _fake_object_info(monkeypatch, *, with_files: bool):
    nodes = {n: {"input": {"required": {}}} for n in videos_router._H3_REQUIRED_NODES}
    def combo(*names):
        return [list(names) if with_files else []]
    nodes["UNETLoader"]["input"]["required"]["unet_name"] = combo(config.H3_UNET_NAME)
    nodes["CLIPLoader"]["input"]["required"]["clip_name"] = combo(config.H3_TEXT_ENCODER_NAME)
    nodes["VAELoader"]["input"]["required"]["vae_name"] = combo(config.H3_VIDEO_VAE_NAME, config.H3_AUDIO_VAE_NAME)
    nodes["LoraLoaderModelOnly"]["input"]["required"]["lora_name"] = combo(config.H3_TURBO_LORA_NAME)

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return nodes

    class _Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, path): return _Resp()

    monkeypatch.setattr(videos_router, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(videos_router.httpx, "Client", _Client)


def test_readiness_reports_files_still_downloading(monkeypatch):
    _fake_object_info(monkeypatch, with_files=False)
    ready, note = videos_router._h3_ready()
    assert not ready and "not in ComfyUI yet" in note and "model" in note


def test_readiness_ok_when_nodes_and_files_present(monkeypatch):
    _fake_object_info(monkeypatch, with_files=True)
    assert videos_router._h3_ready() == (True, None)


def test_creating_an_h3_video_is_refused_with_a_reason_until_ready(monkeypatch):
    _fake_object_info(monkeypatch, with_files=False)
    with TestClient(app) as c:
        assert c.post("/api/auth/signup", json={"username": "h3_user", "password": "h3password1", "name": "H"}).status_code == 201
        project_id = c.post("/api/projects", json={"name": "H3 test"}).json()["id"]
        body = {"project_id": project_id, "motion_preset": "subtle_breathing", "provider": "local_h3", "prompt": "a calm sea"}
        r = c.post("/api/videos", json={**body, "mode": "text_to_video", "duration_seconds": 5})
        assert r.status_code == 409 and "MiniMax H3 is not ready" in r.json()["detail"]
        r = c.post("/api/videos", json={**body, "mode": "video_upscale"})
        assert r.status_code == 409 and "Text -> Video and Image -> Video" in r.json()["detail"]
