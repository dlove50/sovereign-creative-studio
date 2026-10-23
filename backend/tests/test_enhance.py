"""Universal Enhance: real ffmpeg on generated media, non-destructive outputs, honesty about missing models."""
import json
import subprocess
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import STORAGE_DIR
from app.main import app
from app.services import enhance
from app.services.music_playback import audio_duration, find_ffmpeg_tool

FFMPEG = find_ffmpeg_tool("ffmpeg")
pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg required")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _wait(client, job_id, timeout=120):
    for _ in range(int(timeout / 0.2)):
        job = client.get(f"/api/enhance/jobs/{job_id}").json()
        if job["status"] in ("done", "error", "cancelled"):
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def _noisy_png(path):
    rng = np.random.default_rng(1)
    base = np.zeros((120, 160, 3), dtype=np.float32)
    base[:, :80] = (40, 60, 90)
    base[:, 80:] = (200, 180, 120)
    noisy = np.clip(base + rng.normal(0, 28, base.shape), 0, 255).astype(np.uint8)
    Image.fromarray(noisy).save(path)
    return path


def test_catalog_marks_models_unavailable_instead_of_faking_them(client):
    ops = {o["id"]: o for o in client.get("/api/enhance/operations").json()["operations"]}
    assert ops["denoise"]["available"] is True
    assert ops["dereverb"]["available"] or ops["dereverb"]["unavailable_reason"]
    assert ops["dereverb"]["engine"] == "cpu:wpe"
    for model_op in ("upscale_ai", "face_restore", "interpolate_ai"):  # installed or honestly explained
        assert ops[model_op]["available"] or ops[model_op]["unavailable_reason"]
    assert "no new detail" in ops["upscale_classic"]["label"]


@pytest.mark.skipif(not enhance._video_available(str(enhance._VIDEO_PYTHON)), reason="CPU OpenCV environment unavailable")
def test_cpu_video_finishing_chains_without_retiming_or_changing_audio(client, tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=160x96:rate=25:duration=1", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=1", "-c:v", "libx264", "-c:a", "aac", str(source)], check=True)
    original = source.read_bytes()
    response = client.post("/api/enhance/jobs", files={"file": (source.name, original)},
                           data={"ops": json.dumps([{"op": "motion_sharpen", "params": {"amount": .5}},
                                                     {"op": "shot_match", "params": {"strength": .5}}])})
    assert response.status_code == 202, response.text
    job = _wait(client, response.json()["id"])
    assert job["status"] == "done", job
    result = client.get(job["outputs"][0]["url"])
    assert result.status_code == 200
    finished = tmp_path / "finished.mp4"
    finished.write_bytes(result.content)
    probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-count_frames", "-show_entries", "stream=nb_read_frames,avg_frame_rate,duration", "-of", "json", str(finished)]))
    stream = probe["streams"][0]
    assert stream["nb_read_frames"] == "25"
    assert stream["avg_frame_rate"] == "25/1"
    assert float(stream["duration"]) == pytest.approx(1)
    def audio_hash(path):
        return subprocess.check_output([FFMPEG, "-v", "error", "-i", str(path), "-map", "0:a", "-f", "md5", "-"])
    assert audio_hash(source) == audio_hash(finished)
    assert source.read_bytes() == original


def test_image_denoise_sharpen_upscale_keeps_the_original(client, tmp_path):
    src = _noisy_png(tmp_path / "photo.png")
    before = src.read_bytes()
    ops = [{"op": "denoise", "params": {"strength": 0.8}}, {"op": "sharpen", "params": {"amount": 0.2}},
           {"op": "upscale_classic", "params": {"target": 720}}]
    r = client.post("/api/enhance/jobs", files={"file": ("photo.png", before)}, data={"ops": json.dumps(ops)})
    assert r.status_code == 202, r.text
    job = _wait(client, r.json()["id"])
    assert job["status"] == "done", job
    out = client.get(job["outputs"][0]["url"])
    assert out.status_code == 200
    out_path = tmp_path / "out.png"
    out_path.write_bytes(out.content)
    img = np.asarray(Image.open(out_path).convert("RGB"), dtype=np.float32)
    assert img.shape[0] == 720
    # Noise inside the flat dark half, per colour channel, drops clearly.
    orig = np.asarray(Image.open(src).convert("RGB"), dtype=np.float32)
    noise_after = img[100:600, 50:400].std(axis=(0, 1)).mean()
    noise_before = orig[10:110, 5:70].std(axis=(0, 1)).mean()
    assert noise_after < noise_before * 0.6, (noise_before, noise_after)
    assert client.get(job["source_url"]).content == before  # original untouched


def test_audio_denoise_and_loudness(client, tmp_path):
    wav = tmp_path / "talk.wav"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=3", "-f", "lavfi",
                    "-i", "anoisesrc=d=3:a=0.02", "-filter_complex", "amix=inputs=2", str(wav)], check=True)
    ops = [{"op": "audio_denoise"}, {"op": "vocal_clarity"}, {"op": "loudness", "params": {"lufs": -16}}]
    r = client.post("/api/enhance/jobs", files={"file": ("talk.wav", wav.read_bytes())}, data={"ops": json.dumps(ops)})
    job = _wait(client, r.json()["id"])
    assert job["status"] == "done", job
    assert job["outputs"][0]["kind"] == "audio"


def test_video_denoise_deflicker_interpolate(client, tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run([FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2", "-f", "lavfi",
                    "-i", "sine=f=440:d=2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)], check=True)
    ops = [{"op": "denoise"}, {"op": "deflicker"}, {"op": "interpolate", "params": {"fps": 50}}]
    r = client.post("/api/enhance/jobs", files={"file": ("clip.mp4", clip.read_bytes())}, data={"ops": json.dumps(ops)})
    job = _wait(client, r.json()["id"], timeout=300)
    assert job["status"] == "done", job
    out = tmp_path / "o.mp4"
    out.write_bytes(client.get(job["outputs"][0]["url"]).content)
    rate = subprocess.run([find_ffmpeg_tool("ffprobe"), "-v", "error", "-select_streams", "v", "-show_entries",
                           "stream=r_frame_rate", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip()
    assert rate == "50/1" and abs(audio_duration(out) - 2) < 0.2


def test_bad_requests_are_refused(client, tmp_path):
    png = _noisy_png(tmp_path / "x.png").read_bytes()
    for ops, msg in (([{"op": "dereverb"}], "does not apply"), ([{"op": "eq"}], "does not apply"),
                     ([{"op": "nope"}], "Unknown")):
        r = client.post("/api/enhance/jobs", files={"file": ("x.png", png)}, data={"ops": json.dumps(ops)})
        assert r.status_code == 400 and msg in r.json()["detail"]
    r = client.post("/api/enhance/jobs/from-library", json={"url": "/storage/../../etc/passwd", "ops": [{"op": "denoise"}]})
    assert r.status_code == 400


def test_library_media_is_referenced_and_survives_delete(client, tmp_path):
    lib = STORAGE_DIR / "library-test"
    lib.mkdir(parents=True, exist_ok=True)
    original = _noisy_png(lib / "keep.png")
    r = client.post("/api/enhance/jobs/from-library", json={"url": "/storage/library-test/keep.png",
                                                            "ops": [{"op": "color"}]})
    job = _wait(client, r.json()["id"])
    assert job["status"] == "done"
    assert client.post(f"/api/enhance/jobs/{job['id']}/apply", json={"index": 0}).json()["applied"]["index"] == 0
    assert client.delete(f"/api/enhance/jobs/{job['id']}").status_code == 204
    assert original.is_file()


def test_presets_round_trip(client):
    saved = client.post("/api/enhance/presets", json={"name": "Podcast", "kind": "audio",
                                                      "ops": [{"op": "audio_denoise"}, {"op": "loudness"}]})
    assert saved.status_code == 201
    preset = next(p for p in saved.json() if p["name"] == "Podcast")
    assert preset["ops"][1]["params"]["lufs"] == -14
    left = client.delete(f"/api/enhance/presets/{preset['id']}").json()
    assert all(p["id"] != preset["id"] for p in left)


def test_ffmpeg_graph_is_built_from_params():
    args = enhance.ffmpeg_args(enhance.Path("a.mp4"), enhance.Path("b.mp4"), "video",
                               [{"op": "upscale_classic", "params": {"target": 2160}},
                                {"op": "loudness", "params": {"lufs": -14}}])
    assert "scale=-2:2160:flags=lanczos" in args and "loudnorm=I=-14:TP=-1.0:LRA=11" in args


def test_passes_group_ffmpeg_ops_and_isolate_models():
    ops = [{"op": "denoise"}, {"op": "color"}, {"op": "upscale_ai"}, {"op": "sharpen"}]
    assert [[o["op"] for o in g] for g in enhance._passes(ops)] == [["denoise", "color"], ["upscale_ai"], ["sharpen"]]


@pytest.mark.skipif(not enhance._available(enhance.OPERATIONS["upscale_ai"])[0], reason="Real-ESRGAN not installed")
def test_real_esrgan_chain_on_gpu(client, tmp_path):
    src = _noisy_png(tmp_path / "small.png")
    ops = [{"op": "denoise", "params": {"strength": 0.5}}, {"op": "upscale_ai", "params": {"scale": 2}}]
    r = client.post("/api/enhance/jobs", files={"file": ("small.png", src.read_bytes())}, data={"ops": json.dumps(ops)})
    job = _wait(client, r.json()["id"], timeout=300)
    assert job["status"] == "done", job
    out = tmp_path / "out.png"
    out.write_bytes(client.get(job["outputs"][0]["url"]).content)
    assert Image.open(out).size == (320, 240)


@pytest.mark.skipif(not enhance._AUDIO_PYTHON.is_file(), reason='optional CPU speech environment not installed')
def test_real_wpe_reduces_synthetic_room_tail_and_preserves_source(tmp_path, client):
    from app.services import performance_engine as pe
    rng = np.random.default_rng(42)
    rate, seconds = 16000, 6
    envelope = np.zeros(rate * seconds)
    for start, end in ((.2,.65),(1,1.45),(2,2.45),(3,3.45),(4,4.45)):
        envelope[int(start*rate):int(end*rate)] = 1
    dry = rng.normal(0,.15,len(envelope)) * envelope
    wet = dry.copy()
    for delay, gain in ((.064,.65),(.128,.45),(.192,.3),(.256,.2)):
        shift = int(delay * rate)
        wet[shift:] += gain * dry[:-shift]
    wet += rng.normal(0,.005,len(wet))  # room noise; not an unrealistically exact zero variance
    source = pe.write_wav(tmp_path/'room.wav', wet)
    before = source.read_bytes()
    output = tmp_path/'clean.wav'
    result = subprocess.run([str(enhance._AUDIO_PYTHON),str(enhance._AUDIO_WORKER),'dereverb',
                             '{"strength":1}',str(source),str(output)],capture_output=True,text=True,timeout=45)
    assert result.returncode == 0, result.stderr
    clean = pe.decode(output)
    t = np.arange(len(clean))/rate
    tail = (t > .68) & (t < .9)
    assert np.sqrt(np.mean(clean[tail]**2)) < .8 * np.sqrt(np.mean(wet[tail]**2))
    assert np.isfinite(clean).all() and len(clean) == len(wet)
    assert source.read_bytes() == before
    response = client.post('/api/enhance/jobs', files={'file': ('room.wav', before)},
                           data={'ops': json.dumps([{'op': 'dereverb', 'params': {'strength': .65}},
                                                    {'op': 'eq', 'params': {'mid': 2}}])})
    assert response.status_code == 202, response.text
    job = _wait(client, response.json()['id'], timeout=45)
    assert job['status'] == 'done', job
    assert client.get(job['source_url']).content == before
    assert client.get(job['outputs'][0]['url']).status_code == 200
