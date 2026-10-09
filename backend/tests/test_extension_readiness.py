import json
from pathlib import Path

import pytest

from app.routers import videos


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(videos, "VIDEO_BACKEND", "comfyui")
    workflow = Path(__file__).parents[1] / "workflows" / "video_extension_ltx.json"
    monkeypatch.setattr(videos, "COMFYUI_VIDEO_EXTENSION_WORKFLOW_PATH", str(workflow))
    monkeypatch.setattr(videos.shutil, "which", lambda tool: tool)
    info = {node["class_type"]: {} for node in json.loads(workflow.read_text()).values()}
    info["CheckpointLoaderSimple"] = {"input": {"required": {"ckpt_name": [[videos.COMFYUI_VIDEO_MODEL_NAME]]}}}
    info["LTXAVTextEncoderLoader"] = {"input": {"required": {"text_encoder": [[videos._TEXT_ENCODER_MODEL]]}}}

    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url): return self
        def raise_for_status(self): pass
        def json(self): return info

    monkeypatch.setattr(videos.httpx, "Client", Client)
    return info


def test_extension_ready_after_live_repair(configured):
    assert videos._video_extension_ready() == (True, None)


def test_extension_requires_last_frame_node(configured):
    del configured["ImageFromBatch"]
    assert videos._video_extension_ready() == (False, "Missing ComfyUI nodes: ImageFromBatch")


def test_extension_requires_assembly_tools(configured, monkeypatch):
    monkeypatch.setattr(videos.shutil, "which", lambda tool: None if tool == "ffmpeg" else tool)
    assert videos._video_extension_ready() == (False, "Video Extension assembly requires: ffmpeg")


def test_extension_requires_checkpoint(configured):
    configured["CheckpointLoaderSimple"] = {}
    ready, reason = videos._video_extension_ready()
    assert not ready
    assert "LTX model not listed" in reason
