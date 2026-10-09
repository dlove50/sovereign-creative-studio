"""Long talking-avatar videos: chunk planning, extend/LoRA graph patching, joining."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

from app import config  # noqa: E402
from app.services import avatar_comfyui as ac  # noqa: E402
from app.services.avatar_presets import resolve_preset  # noqa: E402

FFMPEG = ac._ffmpeg()


def test_short_speech_is_one_chunk_fitted_to_4n_plus_1():
    plans, total = ac.plan_chunks(1.0, chunk_frames=81)
    assert total == 25
    assert plans == [ac.ChunkPlan(0, 25, 25, False)]


def test_long_speech_chains_overlapping_chunks():
    plans, total = ac.plan_chunks(10.0, chunk_frames=81)  # 250 frames
    assert total == 250
    # 81 + 72 * 3 = 297 >= 250 -> one base chunk + three extensions
    assert [p.extends for p in plans] == [False, True, True, True]
    # Each extension's audio starts where the previous chunk started (node offset = 81 - 9).
    assert [p.audio_start_frame for p in plans] == [0, 0, 72, 144]
    assert all(p.audio_frames == 153 for p in plans[1:])
    new_frames = plans[0].length + sum(p.length - ac.MOTION_FRAMES for p in plans[1:])
    assert new_frames >= total


def _workflow():
    path = ac._workflow_path()
    return ac._sanitize(json.loads(path.read_text(encoding="utf-8")), path)


def test_extend_chunk_feeds_previous_video_frames():
    patched = ac._patch(_workflow(), "img.png", "a.wav", "hi", resolve_preset("quality"), length=81, prev_video_name="prev.mp4")
    talk = next(n for n in patched.values() if n["class_type"] == ac._TALK_NODE)
    assert talk["inputs"]["length"] == 81
    assert talk["inputs"]["previous_frames"] == [ac._PREV_FRAMES_ID, 0]
    assert patched[ac._PREV_LOADER_ID] == {"class_type": "LoadVideo", "inputs": {"file": "prev.mp4"}}


def test_lora_is_inserted_only_when_configured(monkeypatch):
    monkeypatch.setattr(config, "AVATAR_WAN_LORA_NAME", "")
    plain = ac._patch(_workflow(), "img.png", "a.wav", "hi")
    assert ac._LORA_ID not in plain

    monkeypatch.setattr(config, "AVATAR_WAN_LORA_NAME", "lightx2v.safetensors")
    patched = ac._patch(_workflow(), "img.png", "a.wav", "hi")
    talk = next(n for n in patched.values() if n["class_type"] == ac._TALK_NODE)
    assert talk["inputs"]["model"] == [ac._LORA_ID, 0]
    assert patched[ac._LORA_ID]["inputs"]["model"] == ["1", 0]
    assert patched[ac._LORA_ID]["inputs"]["lora_name"] == "lightx2v.safetensors"


@pytest.mark.skipif(not FFMPEG, reason="FFmpeg not installed")
def test_join_drops_overlap_and_matches_speech_length(tmp_path):
    def make(name: str, frames: int, args: list[str]) -> str:
        out = tmp_path / name
        subprocess.run([FFMPEG, "-y", "-v", "error", *args, "-frames:v", str(frames), str(out)], check=True)
        return out

    chunks = [
        make("c0.mp4", 81, ["-f", "lavfi", "-i", "testsrc=size=64x64:rate=25", "-pix_fmt", "yuv420p"]),
        make("c1.mp4", 81, ["-f", "lavfi", "-i", "testsrc=size=64x64:rate=25", "-pix_fmt", "yuv420p"]),
    ]
    audio = tmp_path / "speech.wav"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=duration=5", str(audio)], check=True)
    out = tmp_path / "joined.mp4"

    ac._join_chunks(chunks, audio, total_frames=125, out_path=out)

    probe = shutil.which("ffprobe") or FFMPEG.replace("ffmpeg", "ffprobe")
    frames = subprocess.run(
        [probe, "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert int(frames) == 125  # 81 + (81 - 9) = 153 available, trimmed to the speech


def test_find_video_ignores_loader_preview_of_previous_chunk():
    # Real ComfyUI history for an extend chunk: LoadVideo (node 90) echoes the
    # previous chunk as an "input" preview before SaveVideo's actual output.
    outputs = {
        "90": {"images": [{"filename": "abc_v0.mp4", "subfolder": "", "type": "input"}], "animated": [True]},
        "11": {"images": [{"filename": "sovereign_avatar_00026_.mp4", "subfolder": "", "type": "output"}], "animated": [True]},
    }
    assert ac._find_video(outputs)["filename"] == "sovereign_avatar_00026_.mp4"


def test_tiny_preset_covers_sofia_full_voice_without_looping():
    plans, total = ac.plan_chunks(3.616, chunk_frames=41)
    assert total == 91
    assert [p.audio_start_frame for p in plans] == [0, 0, 32]
    assert [p.extends for p in plans] == [False, True, True]
    assert plans[0].length + sum(p.length - ac.MOTION_FRAMES for p in plans[1:]) == 105



@pytest.mark.parametrize("size", [(256, 256), (480, 832), (832, 480)])
def test_portrait_frame_contains_top_and_bottom_without_modifying_source(tmp_path, size):
    from PIL import Image, ImageDraw
    source = tmp_path / "portrait.png"
    image = Image.new("RGB", (100, 200), "green")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 99, 19), fill="red")
    draw.rectangle((0, 180, 99, 199), fill="blue")
    image.save(source)
    before = source.read_bytes()
    output = tmp_path / "framed.png"
    ac._prepare_avatar_frame(source, output, *size)
    with Image.open(output) as framed:
        assert framed.size == size
        contained_height = min(size[1], size[0] * 2)
        top = (size[1] - contained_height) // 2
        assert framed.getpixel((size[0] // 2, top + 3)) == (255, 0, 0)
        assert framed.getpixel((size[0] // 2, top + contained_height - 4)) == (0, 0, 255)
        assert framed.getpixel((0, size[1] // 2)) == (24, 24, 24)
    assert source.read_bytes() == before

@pytest.mark.parametrize("seconds", [0.4, 3.616])
def test_independent_generations_reference_isolated_uploads(tmp_path, monkeypatch, seconds):
    import asyncio
    from PIL import Image
    source = tmp_path / "portrait.png"
    Image.new("RGB", (40, 80), "green").save(source)
    audio = tmp_path / "voice.wav"
    audio.write_bytes(b"fixture")
    uploads, graphs = [], []

    class Response:
        def __init__(self, name): self.name = name
        def raise_for_status(self): pass
        def json(self): return {"name": "server_" + self.name, "subfolder": "isolated"}

    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, files, data):
            assert url == "/upload/image"
            name = next(iter(files.values()))[0]
            uploads.append(name)
            return Response(name)

    async def render(client, graph, path):
        graphs.append(graph)
        path.write_bytes(b"video fixture")

    monkeypatch.setattr(ac.httpx, "AsyncClient", Client)
    monkeypatch.setattr(ac, "_audio_seconds", lambda _: seconds)
    monkeypatch.setattr(ac, "_render", render)
    monkeypatch.setattr(ac, "_slice_audio", lambda src, plan, dst: dst.write_bytes(b"audio fixture"))
    monkeypatch.setattr(ac, "_join_chunks", lambda chunks, audio, frames, out: out.write_bytes(b"joined fixture"))
    for i in range(2):
        asyncio.run(ac.generate_talking_avatar(source, audio, "hello", tmp_path / f"out{i}.mp4", resolve_preset("tiny_test")))
    images = [name for name in uploads if name.endswith(".png")]
    assert len(images) == len(set(images)) == 2
    chunk_uploads = [name for name in uploads if "_a" in name or "_v" in name]
    assert len(chunk_uploads) == len(set(chunk_uploads))
    for graph in graphs:
        assert graph["4"]["inputs"]["image"] in ["isolated/server_" + name for name in images]
        assert graph["12"]["inputs"]["audio"] in ["isolated/server_" + name for name in uploads if name.endswith(".wav")]
        if ac._PREV_LOADER_ID in graph:
            assert graph[ac._PREV_LOADER_ID]["inputs"]["file"] in ["isolated/server_" + name for name in chunk_uploads]
    assert graphs[0]["4"]["inputs"]["image"] != graphs[-1]["4"]["inputs"]["image"]
