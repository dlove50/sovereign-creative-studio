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
    assert wf["7"]["class_type"] == "SovereignInfiniteTalkParallel"  # voices on one timeline, not turn-taking
    assert wf[talk["audio_encoder_output_1"][0]]["inputs"]["audio"] == ["12", 0] and wf["12"]["inputs"]["audio"] == "a.wav"
    assert wf[talk["mode.audio_encoder_output_2"][0]]["inputs"]["audio"] == ["22", 0] and wf["22"]["inputs"]["audio"] == "b.wav"
    assert wf[talk["mode.mask_1"][0]]["inputs"]["image"] == "m0.png"
    assert wf[talk["mode.mask_2"][0]]["inputs"]["image"] == "m1.png"
    single = pr.build_workflow(image="s.png", audios=["a.wav"], masks=[], prompt="p", seed=1, length=81)
    assert single["7"]["inputs"]["mode"] == "single_speaker" and "22" not in single
    assert single["7"]["class_type"] == "WanInfiniteTalkToVideo"


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
    monkeypatch.setattr(pr, "UPSCALE", 0)  # the Real-ESRGAN pass is covered separately
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


def test_upscale_is_skipped_not_faked_when_unavailable(tmp_path, monkeypatch):
    from app.services import enhance
    monkeypatch.setattr(enhance, "_available", lambda op: (False, "missing"))
    src = tmp_path / "in.mp4"
    src.write_bytes(b"x")
    assert pr._upscale("abc", src, tmp_path / "out.mp4") is None
    assert not (tmp_path / "out.mp4").exists()


def test_layer_cache_tracks_performer_inputs_not_camera(duet):
    import copy
    for p in duet['performers']:
        pe.build_drive_audio(duet, p['id'])
    a, b = duet['performers']
    original = [pr._layer_key(duet, p) for p in (a, b)]
    duet['camera'] = [{'start': 0, 'end': 6, 'shot': 'close_up', 'focus': a['id']}]
    assert [pr._layer_key(duet, p) for p in (a, b)] == original
    a['motion']['hands'] = .9
    assert pr._layer_key(duet, a) != original[0]
    assert pr._layer_key(duet, b) == original[1]
    changed = copy.deepcopy(duet)
    changed['performers'][1]['stage']['scale'] = .8
    assert pr._layer_key(changed, changed['performers'][1]) != original[1]


@pytest.mark.skipif(not FFMPEG, reason='ffmpeg required')
def test_independent_layers_reuse_and_selectively_regenerate(duet, monkeypatch):
    import asyncio
    submitted = []
    async def fake_upload(client, local, kind):
        return local.name
    async def fake_submit(client, workflow, out, project_id):
        submitted.append(workflow)
        color = 'red' if len(submitted) == 1 else 'blue'
        subprocess.run([FFMPEG, '-y', '-v', 'error', '-f', 'lavfi', '-i',
                        f'color=c={color}:s={pr.WIDTH}x{pr.HEIGHT}:r=25',
                        '-frames:v', str(workflow['7']['inputs']['length']),
                        '-pix_fmt', 'yuv420p', str(out)], check=True)
    monkeypatch.setattr(pr, '_upload', fake_upload)
    monkeypatch.setattr(pr, '_submit', fake_submit)
    monkeypatch.setattr(pr, 'CHUNK_FRAMES', 201)
    monkeypatch.setattr(pr, 'UPSCALE', 0)
    def fake_matte(source, target):
        if target.suffix == '.png':
            import shutil
            shutil.copyfile(source, target)
            return target
        # Preserve transparent background in the real encoded layer and exercise alpha composition.
        from PIL import ImageDraw
        image = Image.new('RGBA', (pr.WIDTH, pr.HEIGHT), (0, 255, 0, 0))
        color = 'red' if source.name.startswith(duet['performers'][0]['id']) else 'blue'
        ImageDraw.Draw(image).rectangle((pr.WIDTH*.35, 0, pr.WIDTH*.65, pr.HEIGHT), fill=color)
        png = target.with_suffix('.png'); image.save(png)
        subprocess.run([FFMPEG, '-y', '-v', 'error', '-loop', '1', '-i', str(png), '-t', '6',
                        '-r', '25', '-c:v', 'ffv1', '-pix_fmt', 'bgra', str(target)], check=True)
        return target
    monkeypatch.setattr(pr, '_matte_layer', fake_matte)
    duet['render_strategy'] = 'independent_layers'
    pe.save(duet)
    asyncio.run(pr._render(duet['id']))
    assert len(submitted) == 2
    assert all(w['7']['inputs']['mode'] == 'single_speaker' for w in submitted)
    project = pe.get(duet['id'])
    layers = project['render']['layers']
    assert not any(p['reused'] for p in layers)
    assert abs(audio_duration(pe.media_dir(duet['id']) / 'performance.mp4') - 6) < .3
    # Read actual encoded pixels, not just the FFmpeg command or manifest.
    frame = subprocess.run([FFMPEG, '-v', 'error', '-i', project['render']['master_shot'],
                            '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                           capture_output=True, check=True).stdout
    pixels = np.frombuffer(frame, dtype=np.uint8).reshape(pr.HEIGHT, pr.WIDTH, 3)
    assert pixels[pr.HEIGHT//2, pr.WIDTH//4, 0] > 200
    assert pixels[pr.HEIGHT//2, 3*pr.WIDTH//4, 2] > 200
    # No generated green background and no rectangular layer obscuring the shared stage.
    center = pixels[pr.HEIGHT//2, pr.WIDTH//2]
    assert center.max() < 180 and center[1] < 150
    assert all(p['alpha_file'].endswith('.mkv') for p in layers)
    asyncio.run(pr._render(duet['id']))
    assert len(submitted) == 2
    project = pe.get(duet['id'])
    assert all(p['reused'] for p in project['render']['layers'])
    assert all(p['alpha_reused'] for p in project['render']['layers'])
    project['performers'][0]['motion']['hands'] = .9
    pe.save(project)
    asyncio.run(pr._render(duet['id']))
    assert len(submitted) == 3
    layers = pe.get(duet['id'])['render']['layers']
    assert [p['reused'] for p in layers] == [False, True]


def test_cancellation_is_scoped_and_never_interrupts_other_jobs():
    import asyncio
    import httpx
    requests = []
    def handle(request):
        requests.append((request.method, request.url.path))
        assert request.url.path == '/api/jobs/ours/cancel'
        return httpx.Response(200, json={'cancelled': True})
    async def run():
        async with httpx.AsyncClient(base_url='http://comfy', transport=httpx.MockTransport(handle)) as client:
            assert await pr._stop_prompt(client, 'ours')
    asyncio.run(run())
    assert requests == [('POST', '/api/jobs/ours/cancel')]


def test_old_server_running_job_does_not_trigger_global_interrupt():
    import asyncio
    import httpx
    def handle(request):
        if request.url.path == '/api/jobs/ours/cancel':
            return httpx.Response(404)
        assert request.method == 'GET' and request.url.path == '/queue'
        return httpx.Response(200, json={'queue_running': [[0, 'ours']], 'queue_pending': []})
    async def run():
        async with httpx.AsyncClient(base_url='http://comfy', transport=httpx.MockTransport(handle)) as client:
            assert not await pr._stop_prompt(client, 'ours')
    asyncio.run(run())


def test_upscale_preflight_releases_idle_models_and_checks_memory():
    import httpx
    seen = []
    def handle(request):
        seen.append((request.method, request.url.path))
        if request.url.path == '/queue':
            return httpx.Response(200, json={'queue_running': [], 'queue_pending': []})
        if request.url.path == '/free':
            assert json.loads(request.content) == {'unload_models': True, 'free_memory': True}
            return httpx.Response(200)
        assert request.url.path == '/system_stats'
        return httpx.Response(200, json={'devices': [{'vram_total': 32*1024**3, 'vram_free': 12*1024**3}]})
    with httpx.Client(base_url='http://comfy', transport=httpx.MockTransport(handle)) as client:
        assert pr._prepare_upscale(client)
    assert seen == [('GET','/queue'),('POST','/free'),('GET','/system_stats')]


def test_upscale_preflight_leaves_other_queued_work_alone():
    import httpx
    def handle(request):
        assert request.method == 'GET' and request.url.path == '/queue'
        return httpx.Response(200, json={'queue_running': [], 'queue_pending': [[1,'other']]})
    with httpx.Client(base_url='http://comfy', transport=httpx.MockTransport(handle)) as client:
        assert not pr._prepare_upscale(client)


def test_motion_cue_uses_retained_song_time_after_extension(monkeypatch):
    monkeypatch.setattr(pr, "CHUNK_FRAMES", 81)
    plans, _ = pr.plan_chunks(75, 81)
    # At the14.4s handoff the extension audio includes the previous origin.
    # That context must not choose MOVING instead of the new SINGING state.
    start, end = pr._visible_chunk_window(plans[5], 75)
    assert start == pytest.approx(14.76)
    assert end == pytest.approx(17.64)
    assert (start + end) / 2 > 14.4
    assert pr._visible_chunk_window(plans[0], 75) == (0, 3.24)
    assert pr._visible_chunk_window(plans[-1], 75)[1] == 75
