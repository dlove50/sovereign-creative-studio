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
