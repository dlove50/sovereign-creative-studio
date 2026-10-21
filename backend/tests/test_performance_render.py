"""Performance renderer: workflow wiring, speaker masks, camera crops, and the full job with a fake ComfyUI."""
import json
import subprocess
import time

import numpy as np
import pytest
from PIL import Image

from app.services import performance_engine as pe, performance_render as pr
from app.services.music_playback import audio_duration, find_ffmpeg_tool
from tests.test_performance_engine import _sung

FFMPEG = find_ffmpeg_tool("ffmpeg")


@pytest.fixture()
def duet(tmp_path):
    a = _sung(6, 0, 3)
    b = _sung(6, 3, 5, freq=330)
    project = pe.create("user-1", "Render duet", ["Ava", "Ben"], "alternating")
    master = pe.write_wav(tmp_path / "m.wav", (a + b) / 2)
    project["master_audio"] = str(master)
    pe.set_duration_from(project, master)
    for p, stem, color in zip(project["performers"], (a, b), ("red", "blue")):
        p["stem"] = str(pe.write_wav(tmp_path / f"{p['id']}.wav", stem))
        img = tmp_path / f"{p['id']}.png"
        Image.new("RGB", (300, 500), color).save(img)
        p["identity_image"] = str(img)
    pe.analyze_stems(project)
    return pe.save(project)


def test_two_speaker_workflow_binds_each_voice_to_its_mask():
    wf = pr.build_workflow(image="s.png", audios=["a.wav", "b.wav"], masks=["m0.png", "m1.png"],
                           prompt="p", seed=7, length=81)
    talk = wf["7"]["inputs"]
    assert talk["mode"] == "two_speakers" and wf["15"]["inputs"]["name"] == pr.MULTI_PATCH
    assert wf[talk["audio_encoder_output_1"][0]]["inputs"]["audio"] == ["12", 0] and wf["12"]["inputs"]["audio"] == "a.wav"
    assert wf[talk["mode.audio_encoder_output_2"][0]]["inputs"]["audio"] == ["22", 0] and wf["22"]["inputs"]["audio"] == "b.wav"
    assert wf[talk["mode.mask_1"][0]]["inputs"]["image"] == "m0.png"
    assert wf[talk["mode.mask_2"][0]]["inputs"]["image"] == "m1.png"
    single = pr.build_workflow(image="s.png", audios=["a.wav"], masks=[], prompt="p", seed=1, length=81)
    assert single["7"]["inputs"]["mode"] == "single_speaker" and "22" not in single


def test_masks_split_the_stage_between_performers(duet, tmp_path):
    left, right = pr.speaker_masks(duet, tmp_path)
    l, r = np.array(Image.open(left)), np.array(Image.open(right))
    assert l[:, : pr.WIDTH // 2 - 2].min() == 255 and l[:, pr.WIDTH // 2 + 2:].max() == 0
    assert (l > 0).sum() + (r > 0).sum() == l.size  # every pixel belongs to exactly one speaker


def test_stage_frame_places_each_identity_on_its_side(duet, tmp_path):
    frame = np.array(Image.open(pr.compose_stage(duet, tmp_path / "f.png")))
    assert frame.shape == (pr.HEIGHT, pr.WIDTH, 3)
    left = frame[-50:, int(pr.WIDTH * 0.33)]
    right = frame[-50:, int(pr.WIDTH * 0.67)]
    assert left[:, 0].mean() > 200 and left[:, 2].mean() < 50   # Ava (red) on the left
    assert right[:, 2].mean() > 200 and right[:, 0].mean() < 50  # Ben (blue) on the right


def test_close_up_crops_on_the_focused_performer(duet):
    ava, ben = duet["performers"]
    w, h, x, _ = pr.crop_for(duet, {"shot": "close_up", "focus": ben["id"]})
    assert w < pr.WIDTH and x + w / 2 > pr.WIDTH / 2
    assert pr.crop_for(duet, {"shot": "wide"}) == (pr.WIDTH, pr.HEIGHT, 0, 0)


def test_prompt_directs_each_side_separately(duet):
    text = pr._prompt_for(duet, 0, 2)
    assert "on the left sings" in text and "on the right mouth closed, listens to Ava" in text


def test_render_refuses_when_inputs_are_missing(duet):
    duet["performers"][1]["identity_image"] = None
    pe.save(duet)
    with pytest.raises(pe.PerformanceError, match="Ben: identity picture"):
        pr.start(duet["id"])


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg required")
def test_full_render_job_with_fake_comfyui(duet, monkeypatch):
    submitted = []

    async def fake_upload(client, local, kind):
        return local.name

    async def fake_submit(client, workflow, out, project_id):
        submitted.append(workflow)
        frames = workflow["7"]["inputs"]["length"]
        subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i",
                        f"testsrc2=s={pr.WIDTH}x{pr.HEIGHT}:r=25", "-frames:v", str(frames),
                        "-pix_fmt", "yuv420p", str(out)], check=True)

    monkeypatch.setattr(pr, "_upload", fake_upload)
    monkeypatch.setattr(pr, "_submit", fake_submit)
    monkeypatch.setattr(pr, "readiness", lambda: [])
    monkeypatch.setattr(pr, "CHUNK_FRAMES", 61)
    pr.start(duet["id"])
    for _ in range(300):
        render = pe.get(duet["id"]).get("render", {})
        if render.get("status") in ("done", "error"):
            break
        time.sleep(0.1)
    assert render["status"] == "done", render
    assert render["chunks"] == len(submitted) >= 2  # 6 s at 25 fps needs more than one 61-frame part
    assert all(w["7"]["inputs"]["mode"] == "two_speakers" for w in submitted)
    assert submitted[1]["7"]["inputs"]["previous_frames"] == ["91", 0]
    seconds = audio_duration(pe.media_dir(duet["id"]) / "performance.mp4")
    assert abs(seconds - duet["duration"]) < 0.3
    probe = subprocess.run([find_ffmpeg_tool("ffprobe"), "-v", "error", "-show_entries", "stream=codec_type,width",
                            "-of", "json", render["video"]], capture_output=True, text=True)
    streams = json.loads(probe.stdout)["streams"]
    assert {s["codec_type"] for s in streams} == {"video", "audio"}
    assert next(s for s in streams if s["codec_type"] == "video")["width"] == pr.WIDTH
