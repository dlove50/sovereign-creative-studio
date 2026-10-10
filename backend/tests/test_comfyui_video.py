"""ComfyUI video adapter tests. HTTP is fully faked; these do not require a
running ComfyUI instance or video model."""
import asyncio
from pathlib import Path

import httpx
import pytest

import app.video_generators as video_generators
import app.video_generators.comfyui as video_mod
from app.video_generators.comfyui import ComfyUIVideoGenerator
from app.video_generators.mock import MockVideoGenerator

WORKFLOW = Path(__file__).resolve().parent.parent / "workflows" / "image_to_video.json"
TEXT_WORKFLOW = (
    Path(__file__).resolve().parent.parent / "workflows" / "text_to_video_ltx.json"
)
UPSCALE_WORKFLOW = (
    Path(__file__).resolve().parent.parent / "workflows" / "video_upscale_ltx.json"
)
V2V_WORKFLOW = (
    Path(__file__).resolve().parent.parent / "workflows" / "video_to_video_ltx.json"
)
EXT_WORKFLOW = (
    Path(__file__).resolve().parent.parent / "workflows" / "video_extension_ltx.json"
)
_SOURCE_BYTES = b"\x89PNG\r\n\x1a\nSOURCE"
_VIDEO_SOURCE_BYTES = b"\x00\x00\x00\x20ftypisomSOURCE"
_VIDEO_BYTES = b"FAKE-MP4"


def _box(name: str, payload: bytes) -> bytes:
    return (len(payload) + 8).to_bytes(4, "big") + name.encode("ascii") + payload


def _minimal_mp4(*, seconds: int = 3, samples: int = 25, width: int = 256, height: int = 256) -> bytes:
    mvhd = b"\x00\x00\x00\x00" + b"\x00" * 8 + (1000).to_bytes(4, "big") + (
        seconds * 1000
    ).to_bytes(4, "big") + b"\x00" * 80
    hdlr = b"\x00\x00\x00\x00" + b"\x00" * 4 + b"vide" + b"\x00" * 20
    tkhd = b"\x00\x00\x00\x00" + b"\x00" * 72 + (width * 65536).to_bytes(
        4, "big"
    ) + (height * 65536).to_bytes(4, "big")
    stsz = b"\x00\x00\x00\x00" + (0).to_bytes(4, "big") + samples.to_bytes(4, "big")
    trak = _box(
        "trak",
        _box("tkhd", tkhd)
        + _box("mdia", _box("hdlr", hdlr) + _box("minf", _box("stbl", _box("stsz", stsz)))),
    )
    return (
        _box("ftyp", b"isom\x00\x00\x02\x00isomiso2avc1mp41")
        + _box("mdat", b"\x00" * 1200)
        + _box("moov", _box("mvhd", mvhd) + trak)
    )


class _FakeResponse:
    def __init__(self, *, json_data=None, content=b""):
        self._json = json_data
        self.content = content
        self.status_code = 200
        self.text = ""

    def json(self):
        return self._json

    def raise_for_status(self):
        return None


class _FakeAsyncClient:
    last_upload_files = None
    last_prompt_json = None
    last_view_params = None
    calls = []

    def __init__(self, *args, **kwargs):
        self.history_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, files=None, data=None):
        _FakeAsyncClient.calls.append(("POST", url))
        if url == "/upload/image":
            _FakeAsyncClient.last_upload_files = files
            return _FakeResponse(
                json_data={"name": "video_input.png", "subfolder": "", "type": "input"}
            )
        if url == "/prompt":
            _FakeAsyncClient.last_prompt_json = json
            return _FakeResponse(json_data={"prompt_id": "vid-123"})
        raise AssertionError(f"unexpected POST {url}")

    async def get(self, url, params=None):
        if url.startswith("/history/"):
            _FakeAsyncClient.calls.append(("GET", url))
            self.history_calls += 1
            if self.history_calls == 1:
                return _FakeResponse(json_data={"vid-123": {}})
            return _FakeResponse(
                json_data={
                    "vid-123": {
                        "outputs": {
                            "12": {
                                "videos": [
                                    {
                                        "filename": "sovereign_video_00001.mp4",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                }
            )
        if url == "/view":
            _FakeAsyncClient.calls.append(("GET", url))
            _FakeAsyncClient.last_view_params = params
            return _FakeResponse(content=_VIDEO_BYTES)
        raise AssertionError(f"unexpected GET {url}")


def _reset_fake_client():
    _FakeAsyncClient.last_upload_files = None
    _FakeAsyncClient.last_prompt_json = None
    _FakeAsyncClient.last_view_params = None
    _FakeAsyncClient.calls = []


def _skip_output_validation(monkeypatch):
    monkeypatch.setattr(
        ComfyUIVideoGenerator,
        "_validate_output_video",
        lambda self, output_path, requested_duration: None,
    )


def _make_source(storage: Path) -> str:
    source = storage / "product-scenes" / "scene.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(_SOURCE_BYTES)
    return "/storage/product-scenes/scene.png"


def _make_video_source(storage: Path) -> str:
    source = storage / "videos" / "source.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(_VIDEO_SOURCE_BYTES)
    return "/storage/videos/source.mp4"


def test_comfyui_video_uploads_injects_polls_and_saves(monkeypatch, tmp_path):
    _reset_fake_client()
    _skip_output_validation(monkeypatch)
    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(video_mod, "_POLL_INTERVAL_SECONDS", 0)

    source_url = _make_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188/",
        str(WORKFLOW),
        "svd_xt.safetensors",
    )
    result = asyncio.run(
        gen.generate(
            video_id="video1",
            source_image_url=source_url,
            prompt="slow cinematic camera push",
            motion_preset="slow_zoom",
            duration_seconds=6,
        )
    )

    assert result.result_url == "/storage/videos/video1.mp4"
    assert (tmp_path / "videos" / "video1.mp4").read_bytes() == _VIDEO_BYTES

    assert _FakeAsyncClient.last_upload_files["image"][0] == "scene.png"
    assert _FakeAsyncClient.last_upload_files["image"][1] == _SOURCE_BYTES

    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    workflow_text = str(posted)
    assert "video_input.png" in workflow_text
    assert "slow cinematic camera push" in workflow_text
    assert "slow_zoom" in workflow_text
    assert "svd_xt.safetensors" in workflow_text
    assert "__SOURCE_IMAGE__" not in workflow_text
    assert "__PROMPT__" not in workflow_text
    assert "__VIDEO_MODEL__" not in workflow_text
    assert posted["7"]["inputs"]["width"] == 640
    assert posted["7"]["inputs"]["height"] == 384
    assert posted["7"]["inputs"]["length"] == 49
    assert posted["9"]["inputs"]["steps"] == 16
    assert posted["11"]["inputs"]["fps"] == 8
    assert posted["13"]["inputs"]["lora_name"] == "ltx-2.3-22b-distilled-lora-384.safetensors"

    assert _FakeAsyncClient.calls == [
        ("POST", "/upload/image"),
        ("POST", "/prompt"),
        ("GET", "/history/vid-123"),
        ("GET", "/history/vid-123"),
        ("GET", "/view"),
    ]
    assert _FakeAsyncClient.last_view_params["filename"] == "sovereign_video_00001.mp4"


def test_comfyui_video_strips_metadata_nodes_before_submit(monkeypatch, tmp_path):
    _reset_fake_client()
    _skip_output_validation(monkeypatch)
    workflow = tmp_path / "with_meta.json"
    workflow.write_text(
        """
{
  "1": {"class_type": "LoadImage", "inputs": {"image": "__SOURCE_IMAGE__"}},
  "2": {"class_type": "LTXVImgToVideo", "inputs": {"image": ["1", 0]}},
  "3": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "__PROMPT__"}},
  "4_meta": {"title": "editor helper", "note": "not executable"}
}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(video_mod, "_POLL_INTERVAL_SECONDS", 0)

    source_url = _make_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188/",
        str(workflow),
        "ltx-2.3-22b-dev-fp8.safetensors",
    )
    asyncio.run(
        gen.generate(
            video_id="video-meta",
            source_image_url=source_url,
            prompt="clean motion",
            motion_preset="slow_zoom",
            duration_seconds=3,
        )
    )

    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    assert "4_meta" not in posted
    assert all("class_type" in node for node in posted.values())


def test_comfyui_text_to_video_skips_upload_injects_and_saves(monkeypatch, tmp_path):
    _reset_fake_client()
    _skip_output_validation(monkeypatch)
    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(video_mod, "_POLL_INTERVAL_SECONDS", 0)

    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188/",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
    )
    result = asyncio.run(
        gen.generate(
            video_id="text-video",
            source_image_url="",
            prompt="luxury product rotating slowly",
            motion_preset="slow_zoom",
            duration_seconds=3,
            mode="text_to_video",
        )
    )

    assert result.result_url == "/storage/videos/text-video.mp4"
    assert (tmp_path / "videos" / "text-video.mp4").read_bytes() == _VIDEO_BYTES
    assert _FakeAsyncClient.last_upload_files is None

    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    workflow_text = str(posted)
    assert "luxury product rotating slowly" in workflow_text
    assert "slow_zoom" in workflow_text
    assert "ltx-2.3-22b-dev-fp8.safetensors" in workflow_text
    assert "__SOURCE_IMAGE__" not in workflow_text
    assert "__PROMPT__" not in workflow_text
    assert "__DURATION_SECONDS__" not in workflow_text
    assert "__VIDEO_MODEL__" not in workflow_text
    assert posted["6"]["inputs"]["width"] == 512
    assert posted["6"]["inputs"]["height"] == 320
    assert posted["5"]["inputs"]["frame_rate"] == 8
    assert posted["6"]["inputs"]["length"] == 25
    assert posted["8"]["inputs"]["steps"] == 12
    assert posted["10"]["inputs"]["fps"] == 8
    assert posted["12"]["inputs"]["lora_name"] == "ltx-2.3-22b-distilled-lora-384.safetensors"

    assert _FakeAsyncClient.calls == [
        ("POST", "/prompt"),
        ("GET", "/history/vid-123"),
        ("GET", "/history/vid-123"),
        ("GET", "/view"),
    ]


def test_comfyui_text_to_video_rejects_ui_format_workflow(tmp_path):
    workflow = tmp_path / "ui_text_format.json"
    workflow.write_text(
        '{"nodes": [{"id": 1, "type": "EmptyLTXVLatentVideo"}], "links": []}',
        encoding="utf-8",
    )
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(workflow),
    )
    with pytest.raises(RuntimeError, match="UI export"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url="",
                prompt="x",
                motion_preset="orbit",
                duration_seconds=3,
                mode="text_to_video",
            )
        )


def test_comfyui_text_to_video_frame_count_tracks_duration():
    assert ComfyUIVideoGenerator._ltx_length_frames(3) == 25
    assert ComfyUIVideoGenerator._ltx_length_frames(5) == 41


def test_comfyui_video_quality_preset_changes_workflow(monkeypatch, tmp_path):
    _reset_fake_client()
    _skip_output_validation(monkeypatch)
    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(video_mod, "_POLL_INTERVAL_SECONDS", 0)

    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188/",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
    )
    asyncio.run(
        gen.generate(
            video_id="preview-video",
            source_image_url="",
            prompt="large dog walking",
            motion_preset="slow_zoom",
            duration_seconds=3,
            mode="text_to_video",
            quality_preset="safe_preview",
        )
    )

    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    assert posted["6"]["inputs"]["width"] == 256
    assert posted["6"]["inputs"]["height"] == 256
    assert posted["8"]["inputs"]["steps"] == 8


def test_comfyui_output_validation_accepts_readable_mp4(tmp_path):
    output = tmp_path / "ok.mp4"
    output.write_bytes(_minimal_mp4(seconds=5, samples=41))

    ComfyUIVideoGenerator._validate_output_video(output, requested_duration=5)


def test_comfyui_output_validation_rejects_short_mp4(tmp_path):
    output = tmp_path / "short.mp4"
    output.write_bytes(_minimal_mp4(seconds=3, samples=9))

    with pytest.raises(RuntimeError, match="shorter-than-requested"):
        ComfyUIVideoGenerator._validate_output_video(output, requested_duration=5)


def test_comfyui_output_validation_rejects_frame_empty_mp4(tmp_path):
    output = tmp_path / "empty.mp4"
    output.write_bytes(_minimal_mp4(seconds=3, samples=0))

    with pytest.raises(RuntimeError, match="no readable video frames"):
        ComfyUIVideoGenerator._validate_output_video(output, requested_duration=3)


def test_comfyui_video_upscale_uploads_video_injects_and_saves(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(video_mod.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout='{"streams":[{"duration":"2.44","nb_read_frames":"61"}]}'))
    _reset_fake_client()
    _skip_output_validation(monkeypatch)
    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(video_mod, "_POLL_INTERVAL_SECONDS", 0)

    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188/",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
        str(UPSCALE_WORKFLOW),
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
    )
    result = asyncio.run(
        gen.generate(
            video_id="upscale-video",
            source_image_url=source_url,
            prompt="upscale validation",
            motion_preset="slow_zoom",
            duration_seconds=3,
            mode="video_upscale",
        )
    )

    assert result.result_url == "/storage/videos/upscale-video.mp4"
    assert (tmp_path / "videos" / "upscale-video.mp4").read_bytes() == _VIDEO_BYTES

    assert _FakeAsyncClient.last_upload_files["image"][0] == "source.mp4"
    assert _FakeAsyncClient.last_upload_files["image"][1] == _VIDEO_SOURCE_BYTES

    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    workflow_text = str(posted)
    assert posted["2"]["class_type"] == "LoadVideo"
    assert posted["6"]["class_type"] == "LTXVLatentUpsampler"
    assert posted["upscale_repeat"]["inputs"]["amount"] == 4
    assert posted["upscale_trim"]["inputs"]["length"] == 61
    assert posted["8"]["inputs"]["audio"] == ["3", 1]
    assert "video_input.png" in workflow_text
    assert "ltx-2.3-22b-dev-fp8.safetensors" in workflow_text
    assert "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" in workflow_text
    assert "__SOURCE_IMAGE__" not in workflow_text
    assert "__VIDEO_MODEL__" not in workflow_text
    assert "__VIDEO_UPSCALE_MODEL__" not in workflow_text

    assert _FakeAsyncClient.calls == [
        ("POST", "/upload/image"),
        ("POST", "/prompt"),
        ("GET", "/history/vid-123"),
        ("GET", "/history/vid-123"),
        ("GET", "/view"),
    ]


@pytest.mark.parametrize("frames,padding", [(1, 0), (57, 0), (61, 4), (64, 1), (65, 0)])
def test_upscale_temporal_padding_preserves_original_count(frames, padding):
    import json
    workflow = json.loads(UPSCALE_WORKFLOW.read_text())
    ComfyUIVideoGenerator._preserve_upscale_frames(workflow, frames)
    assert workflow["upscale_trim"]["inputs"]["length"] == frames
    assert (frames + padding - 1) % 8 == 0
    if padding:
        assert workflow["upscale_repeat"]["inputs"]["amount"] == padding
        assert workflow["4"]["inputs"]["pixels"] == ["upscale_pad", 0]
    else:
        assert "upscale_repeat" not in workflow
        assert workflow["4"]["inputs"]["pixels"] == ["3", 0]


def test_comfyui_video_upscale_requires_upscale_model(tmp_path):
    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
        str(UPSCALE_WORKFLOW),
        "",
    )
    with pytest.raises(RuntimeError, match="COMFYUI_VIDEO_UPSCALE_MODEL_NAME"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="slow_zoom",
                duration_seconds=3,
                mode="video_upscale",
            )
        )


def test_comfyui_video_upscale_missing_workflow_has_clear_error(tmp_path):
    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
        str(tmp_path / "missing_upscale.json"),
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
    )
    with pytest.raises(RuntimeError, match="workflow not found"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="slow_zoom",
                duration_seconds=3,
                mode="video_upscale",
            )
        )


def test_comfyui_video_upscale_rejects_ui_format_workflow(tmp_path):
    workflow = tmp_path / "ui_upscale_format.json"
    workflow.write_text(
        '{"nodes": [{"id": 1, "type": "LoadVideo"}], "links": []}',
        encoding="utf-8",
    )
    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
        str(workflow),
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
    )
    with pytest.raises(RuntimeError, match="UI export"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="slow_zoom",
                duration_seconds=3,
                mode="video_upscale",
            )
        )


def test_comfyui_video_to_video_uploads_video_injects_and_saves(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(video_mod.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout='{"streams":[{"duration":"1.0"}]}'))
    _reset_fake_client()
    _skip_output_validation(monkeypatch)
    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(video_mod, "_POLL_INTERVAL_SECONDS", 0)

    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188/",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
        str(UPSCALE_WORKFLOW),
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        str(V2V_WORKFLOW),
    )
    result = asyncio.run(
        gen.generate(
            video_id="v2v-video",
            source_image_url=source_url,
            prompt="restyle with premium blue lighting",
            motion_preset="slow_zoom",
            duration_seconds=3,
            mode="video_to_video",
        )
    )

    assert result.result_url == "/storage/videos/v2v-video.mp4"
    assert (tmp_path / "videos" / "v2v-video.mp4").read_bytes() == _VIDEO_BYTES

    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    workflow_text = str(posted)
    assert posted["2"]["class_type"] == "LoadVideo"
    assert posted["8"]["class_type"] == "VAEEncodeTiled"
    assert posted["10"]["class_type"] == "KSampler"
    assert posted["10"]["inputs"]["denoise"] == 0.35
    assert "restyle with premium blue lighting" in workflow_text
    assert "ltx-2.3-22b-dev-fp8.safetensors" in workflow_text
    assert "__SOURCE_IMAGE__" not in workflow_text
    assert "__PROMPT__" not in workflow_text
    assert "__VIDEO_MODEL__" not in workflow_text

    assert _FakeAsyncClient.calls == [
        ("POST", "/upload/image"),
        ("POST", "/prompt"),
        ("GET", "/history/vid-123"),
        ("GET", "/history/vid-123"),
        ("GET", "/view"),
    ]


def test_comfyui_video_to_video_missing_workflow_has_clear_error(tmp_path):
    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
        str(UPSCALE_WORKFLOW),
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        str(tmp_path / "missing_v2v.json"),
    )
    with pytest.raises(RuntimeError, match="workflow not found"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="slow_zoom",
                duration_seconds=3,
                mode="video_to_video",
            )
        )


def test_comfyui_video_to_video_rejects_ui_format_workflow(tmp_path):
    workflow = tmp_path / "ui_v2v_format.json"
    workflow.write_text(
        '{"nodes": [{"id": 1, "type": "LoadVideo"}], "links": []}',
        encoding="utf-8",
    )
    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
        str(UPSCALE_WORKFLOW),
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        str(workflow),
    )
    with pytest.raises(RuntimeError, match="UI export"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="slow_zoom",
                duration_seconds=3,
                mode="video_to_video",
            )
        )


def test_comfyui_video_extension_uploads_video_extends_and_saves(monkeypatch, tmp_path):
    _reset_fake_client()
    _skip_output_validation(monkeypatch)
    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(video_mod, "_POLL_INTERVAL_SECONDS", 0)

    def assemble(source, continuation, destination):
        assert source.read_bytes() == _VIDEO_SOURCE_BYTES
        assert continuation.read_bytes() == _VIDEO_BYTES
        destination.write_bytes(b"assembled-original-and-continuation")
        return 10.0

    monkeypatch.setattr(video_mod, "append_continuation", assemble)

    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188/",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
        str(UPSCALE_WORKFLOW),
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        str(V2V_WORKFLOW),
        video_extension_workflow_path=str(EXT_WORKFLOW),
    )
    result = asyncio.run(
        gen.generate(
            video_id="ext-video",
            source_image_url=source_url,
            prompt="continue the clip with more rotation",
            motion_preset="slow_zoom",
            duration_seconds=5,
            mode="video_extension",
        )
    )

    assert result.result_url == "/storage/videos/ext-video.mp4"
    assert (tmp_path / "videos" / "ext-video.mp4").read_bytes() == b"assembled-original-and-continuation"

    assert _FakeAsyncClient.last_upload_files["image"][0] == "source.mp4"
    assert _FakeAsyncClient.last_upload_files["image"][1] == _VIDEO_SOURCE_BYTES

    posted = _FakeAsyncClient.last_prompt_json["prompt"]
    workflow_text = str(posted)
    assert posted["2"]["class_type"] == "LoadVideo"
    assert posted["14"]["class_type"] == "ImageScale"
    assert posted["15"]["class_type"] == "EmptyLTXVLatentVideo"
    assert posted["8"]["class_type"] == "LTXVAddGuide"
    # duration 5s -> LTX 8k+1 grid -> 121 target frames (longer than any short input).
    assert posted["15"]["inputs"]["length"] == 121
    assert "continue the clip with more rotation" in workflow_text
    assert "ltx-2.3-22b-dev-fp8.safetensors" in workflow_text
    assert "__SOURCE_IMAGE__" not in workflow_text
    assert "__PROMPT__" not in workflow_text
    assert "__VIDEO_MODEL__" not in workflow_text
    assert "__VIDEO_LENGTH_FRAMES__" not in workflow_text

    assert _FakeAsyncClient.calls == [
        ("POST", "/upload/image"),
        ("POST", "/prompt"),
        ("GET", "/history/vid-123"),
        ("GET", "/history/vid-123"),
        ("GET", "/view"),
    ]


def test_comfyui_video_extension_missing_workflow_has_clear_error(tmp_path):
    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
        str(UPSCALE_WORKFLOW),
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        str(V2V_WORKFLOW),
        video_extension_workflow_path=str(tmp_path / "missing_ext.json"),
    )
    with pytest.raises(RuntimeError, match="workflow not found"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="slow_zoom",
                duration_seconds=5,
                mode="video_extension",
            )
        )


def test_comfyui_video_extension_requires_model(tmp_path):
    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188",
        str(WORKFLOW),
        "",
        str(TEXT_WORKFLOW),
        str(UPSCALE_WORKFLOW),
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        str(V2V_WORKFLOW),
        video_extension_workflow_path=str(EXT_WORKFLOW),
    )
    with pytest.raises(RuntimeError, match="COMFYUI_VIDEO_MODEL_NAME"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="slow_zoom",
                duration_seconds=5,
                mode="video_extension",
            )
        )


def test_comfyui_video_extension_rejects_ui_format_workflow(tmp_path):
    workflow = tmp_path / "ui_ext_format.json"
    workflow.write_text(
        '{"nodes": [{"id": 1, "type": "LTXVAddGuide"}], "links": []}',
        encoding="utf-8",
    )
    source_url = _make_video_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188",
        str(WORKFLOW),
        "ltx-2.3-22b-dev-fp8.safetensors",
        str(TEXT_WORKFLOW),
        str(UPSCALE_WORKFLOW),
        "ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
        str(V2V_WORKFLOW),
        video_extension_workflow_path=str(workflow),
    )
    with pytest.raises(RuntimeError, match="UI export"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="slow_zoom",
                duration_seconds=5,
                mode="video_extension",
            )
        )


def test_comfyui_video_rejects_ui_format_workflow(tmp_path):
    source_url = _make_source(tmp_path)
    workflow = tmp_path / "ui_format.json"
    workflow.write_text(
        '{"nodes": [{"id": 1, "type": "LoadImage"}], "links": []}',
        encoding="utf-8",
    )
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188", str(workflow), "ltx-2.3-22b-dev-fp8.safetensors"
    )
    with pytest.raises(RuntimeError, match="UI export"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="orbit",
                duration_seconds=4,
            )
        )


def test_comfyui_video_missing_workflow_has_clear_error(tmp_path):
    source_url = _make_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188",
        str(tmp_path / "missing.json"),
        "svd.safetensors",
    )
    with pytest.raises(RuntimeError, match="workflow not found"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="orbit",
                duration_seconds=4,
            )
        )


def test_comfyui_video_requires_model_when_workflow_uses_placeholder(tmp_path):
    source_url = _make_source(tmp_path)
    gen = ComfyUIVideoGenerator("http://comfy.local:8188", str(WORKFLOW), "")
    with pytest.raises(RuntimeError, match="COMFYUI_VIDEO_MODEL_NAME"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="orbit",
                duration_seconds=4,
            )
        )


def test_comfyui_video_missing_video_nodes_has_clear_error(tmp_path):
    source_url = _make_source(tmp_path)
    workflow = tmp_path / "not_video.json"
    workflow.write_text(
        """
{
  "1": {"class_type": "LoadImage", "inputs": {"image": "__SOURCE_IMAGE__"}},
  "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "__PROMPT__"}}
}
""",
        encoding="utf-8",
    )
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188", str(workflow), "svd.safetensors"
    )
    with pytest.raises(RuntimeError, match="video nodes/models"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="orbit",
                duration_seconds=4,
            )
        )


def test_comfyui_video_no_video_output_raises(monkeypatch, tmp_path):
    class _NoVideoClient(_FakeAsyncClient):
        async def get(self, url, params=None):
            if url.startswith("/history/"):
                return _FakeResponse(
                    json_data={
                        "vid-123": {
                            "outputs": {
                                "9": {
                                    "images": [
                                        {
                                            "filename": "plain_image.png",
                                            "subfolder": "",
                                            "type": "output",
                                        }
                                    ]
                                }
                            }
                        }
                    }
                )
            raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _NoVideoClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    source_url = _make_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188", str(WORKFLOW), "svd.safetensors"
    )
    with pytest.raises(RuntimeError, match="No output video found"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="handheld",
                duration_seconds=4,
            )
        )


def test_comfyui_video_timeout_has_clear_error(monkeypatch, tmp_path):
    class _NeverFinishesClient(_FakeAsyncClient):
        async def get(self, url, params=None):
            if url.startswith("/history/"):
                return _FakeResponse(json_data={"vid-123": {}})
            raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _NeverFinishesClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr(video_mod, "_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(video_mod, "_POLL_MAX_ATTEMPTS", 1)
    source_url = _make_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188", str(WORKFLOW), "svd.safetensors"
    )
    with pytest.raises(TimeoutError, match="timed out"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="handheld",
                duration_seconds=4,
            )
        )


def test_comfyui_video_history_error_has_clear_error(monkeypatch, tmp_path):
    class _HistoryErrorClient(_FakeAsyncClient):
        async def get(self, url, params=None):
            if url.startswith("/history/"):
                return _FakeResponse(
                    json_data={
                        "vid-123": {
                            "outputs": {},
                            "status": {
                                "status_str": "error",
                                "messages": [
                                    [
                                        "execution_error",
                                        {
                                            "node_type": "CheckpointLoaderSimple",
                                            "exception_message": "model shape mismatch",
                                        },
                                    ]
                                ],
                            },
                        }
                    }
                )
            raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _HistoryErrorClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    source_url = _make_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188", str(WORKFLOW), "svd.safetensors"
    )
    with pytest.raises(
        RuntimeError, match="failed at CheckpointLoaderSimple: model shape mismatch"
    ):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="orbit",
                duration_seconds=4,
            )
        )


def test_comfyui_video_offline_has_clear_error(monkeypatch, tmp_path):
    class _OfflineClient(_FakeAsyncClient):
        async def post(self, url, json=None, files=None, data=None):
            raise httpx.ConnectError("no route")

    monkeypatch.setattr(video_mod.httpx, "AsyncClient", _OfflineClient)
    monkeypatch.setattr(video_mod, "STORAGE_DIR", tmp_path)
    source_url = _make_source(tmp_path)
    gen = ComfyUIVideoGenerator(
        "http://comfy.local:8188", str(WORKFLOW), "svd.safetensors"
    )
    with pytest.raises(RuntimeError, match="ComfyUI is offline"):
        asyncio.run(
            gen.generate(
                video_id="x",
                source_image_url=source_url,
                prompt="x",
                motion_preset="orbit",
                duration_seconds=4,
            )
        )


def test_video_factory_returns_comfyui_when_selected(monkeypatch):
    monkeypatch.setattr(video_generators, "VIDEO_BACKEND", "comfyui")
    assert isinstance(video_generators.get_video_generator(), ComfyUIVideoGenerator)


def test_video_factory_routes_wan_provider_to_wan_assets(monkeypatch):
    monkeypatch.setattr(video_generators, "VIDEO_BACKEND", "comfyui")
    monkeypatch.setattr(video_generators, "COMFYUI_WAN_VIDEO_WORKFLOW_PATH", "wan.json")
    monkeypatch.setattr(video_generators, "COMFYUI_WAN_VIDEO_MODEL_NAME", "wan.safetensors")

    generator = video_generators.get_video_generator(provider="local_wan")

    assert isinstance(generator, ComfyUIVideoGenerator)
    assert generator.workflow_path.name == "wan.json"
    assert generator.model_name == "wan.safetensors"


def test_video_factory_falls_back_to_mock(monkeypatch):
    monkeypatch.setattr(video_generators, "VIDEO_BACKEND", "mock")
    assert isinstance(video_generators.get_video_generator(), MockVideoGenerator)
    monkeypatch.setattr(video_generators, "VIDEO_BACKEND", "banana")
    assert isinstance(video_generators.get_video_generator(), MockVideoGenerator)


def test_video_output_ignores_loader_input_before_saved_output():
    saved = {"filename": "result.mp4", "subfolder": "", "type": "output"}
    outputs = {
        "loader": {"videos": [{"filename": "source.mp4", "type": "input"}]},
        "save": {"videos": [saved]},
    }
    assert ComfyUIVideoGenerator._first_video_output(outputs) == saved
