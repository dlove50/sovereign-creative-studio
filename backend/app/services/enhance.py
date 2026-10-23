"""Universal AI Enhance: one non-destructive pipeline for images, audio and video.

Select media -> pick operations (or a saved preset) -> render a NEW file -> compare -> apply.
The source file is never modified; every result is a separate version that records exactly
which operations and settings produced it.

Engines
  * ffmpeg  - real, always-available signal processing (denoise, deflicker, sharpen, colour,
              loudness, EQ, stereo, mastering chain, classic upscale, motion interpolation).
  * demucs  - vocal / instrumental separation (the Music Lab stems worker).
  * cpu:wpe - speech dereverberation in an isolated CPU-only environment.
  * model:* - AI models (Real-ESRGAN, GFPGAN, RIFE). Listed with `available: False` and the
              reason until their weights are installed; they are never shown as working.

Honesty rules: classic upscaling and interpolation are labelled as such; nothing claims to
"recover" detail that a model only generates.
"""
from __future__ import annotations

import json
from functools import lru_cache
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import config
from .gpu_jobs import GPU_JOB_LOCK
from ..config import STORAGE_DIR
from .music_playback import audio_duration, find_ffmpeg_tool

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
AUDIO_EXT = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac", ".opus"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
MAX_OPS = 12
JOB_TIMEOUT = 6 * 3600

_lock = threading.Lock()
_procs: dict[str, subprocess.Popen] = {}
_cancelled: set[str] = set()
_running: set[str] = set()
_ID = re.compile(r"^[a-z0-9]{1,32}$")


class EnhanceError(ValueError):
    """A user-presentable reason an enhancement cannot be done."""


def P(id_: str, label: str, lo: float, hi: float, default: float, step: float = 0.05) -> dict[str, Any]:
    return {"id": id_, "label": label, "min": lo, "max": hi, "default": default, "step": step}


# Each op: kind(s), label, engine, params, and an ffmpeg builder (params -> filter string).
OPERATIONS: dict[str, dict[str, Any]] = {
    # --- image + video ----------------------------------------------------------------------
    "denoise": {"kinds": ["image", "video"], "label": "Noise reduction", "engine": "ffmpeg",
                "params": [P("strength", "Strength", 0, 1, 0.4)]},
    "sharpen": {"kinds": ["image", "video"], "label": "Sharpening", "engine": "ffmpeg",
                "params": [P("amount", "Amount", 0, 1, 0.35)]},
    "deblock": {"kinds": ["image", "video"], "label": "Compression artifact reduction", "engine": "ffmpeg", "params": []},
    "color": {"kinds": ["image", "video"], "label": "Colour correction", "engine": "ffmpeg",
              "params": [P("saturation", "Saturation", 0.5, 1.6, 1.08), P("contrast", "Contrast", 0.7, 1.5, 1.05),
                         P("warmth", "Warmth", -1, 1, 0.0)]},
    "low_light": {"kinds": ["image", "video"], "label": "Low-light enhancement", "engine": "ffmpeg",
                  "params": [P("lift", "Shadow lift", 0, 1, 0.45)]},
    "upscale_classic": {"kinds": ["image", "video"], "label": "Upscale (classic Lanczos, no new detail)",
                        "engine": "ffmpeg", "params": [P("target", "Target height", 720, 2160, 1080, 360)]},
    "upscale_ai": {"kinds": ["image", "video"], "label": "AI upscale (Real-ESRGAN)", "engine": "model:realesrgan",
                   "params": [P("scale", "Scale", 2, 4, 2, 2)]},
    "face_restore": {"kinds": ["image", "video"], "label": "Face restoration (GFPGAN)", "engine": "model:gfpgan",
                     "params": [P("fidelity", "Identity fidelity", 0, 1, 0.7)]},
    # --- video only ---------------------------------------------------------------------------
    "motion_sharpen": {"kinds": ["video"], "label": "Motion-aware sharpening (CPU)", "engine": "cpu:video",
                       "params": [P("amount", "Amount", 0, 1, 0.35)]},
    "shot_match": {"kinds": ["video"], "label": "Match shot colours to first shot (CPU)", "engine": "cpu:video",
                   "params": [P("strength", "Match strength", 0, 1, 0.5)]},
    "deflicker": {"kinds": ["video"], "label": "Flicker reduction", "engine": "ffmpeg",
                  "params": [P("window", "Window (frames)", 2, 15, 5, 1)]},
    "interpolate": {"kinds": ["video"], "label": "Frame interpolation (motion-compensated)", "engine": "ffmpeg",
                    "params": [P("fps", "Target fps", 30, 60, 50, 1)]},
    "interpolate_ai": {"kinds": ["video"], "label": "AI frame interpolation (RIFE)", "engine": "model:rife",
                       "params": [P("fps", "Target fps", 30, 120, 60, 1)]},
    # --- audio ----------------------------------------------------------------------------------
    "audio_denoise": {"kinds": ["audio"], "label": "Background noise reduction", "engine": "ffmpeg",
                      "params": [P("strength", "Strength", 0, 1, 0.5)]},
    "vocal_clarity": {"kinds": ["audio"], "label": "Vocal clarity", "engine": "ffmpeg",
                      "params": [P("presence", "Presence", 0, 1, 0.5)]},
    "eq": {"kinds": ["audio"], "label": "EQ / tonal correction", "engine": "ffmpeg",
           "params": [P("bass", "Bass (dB)", -12, 12, 0, 0.5), P("mid", "Mid (dB)", -12, 12, 0, 0.5),
                      P("treble", "Treble (dB)", -12, 12, 0, 0.5)]},
    "stereo": {"kinds": ["audio"], "label": "Stereo width", "engine": "ffmpeg",
               "params": [P("width", "Width", 0, 2.5, 1.3)]},
    "loudness": {"kinds": ["audio", "video"], "label": "Loudness normalisation", "engine": "ffmpeg",
                 "params": [P("lufs", "Target LUFS", -24, -9, -14, 1)]},
    "master": {"kinds": ["audio"], "label": "Mastering assist (glue compression + limiter)", "engine": "ffmpeg",
               "params": [P("drive", "Drive", 0, 1, 0.4)]},
    "dereverb": {"kinds": ["audio"], "label": "Speech reverb reduction (WPE, CPU)", "engine": "cpu:wpe",
                 "params": [P("strength", "Strength", 0, 1, 0.65)]},
    "separate": {"kinds": ["audio", "video"], "label": "Separate vocals / instrumental (Demucs)", "engine": "demucs",
                 "params": []},
}

MODEL_HINTS = {
    "realesrgan": "Install Real-ESRGAN weights (BSD-3) to enable.",
    "gfpgan": "Install GFPGAN v1.4 weights (Apache-2.0) to enable.",
    "rife": "Install RIFE v4 weights (MIT) to enable.",
}


ENHANCE_MODELS = Path(os.getenv("SOVEREIGN_ENHANCE_MODELS", "/mnt/storage/AI-Models/enhance"))
UPSCALE_MODELS = Path(os.getenv("SOVEREIGN_UPSCALE_MODELS", "/mnt/storage/AI-Models/comfyui/upscale_models"))
MODEL_FILES = {
    "realesrgan": [UPSCALE_MODELS / "RealESRGAN_x2plus.pth", UPSCALE_MODELS / "RealESRGAN_x4plus.safetensors"],
    "gfpgan": [ENHANCE_MODELS / "gfpgan" / "GFPGANv1.4.pth", ENHANCE_MODELS / "facexlib" / "detection_Resnet50_Final.pth",
               ENHANCE_MODELS / "facexlib" / "parsing_parsenet.pth"],
    "rife": [ENHANCE_MODELS / "rife" / "RIFEv4.26_0921" / "flownet.pkl"],
}
_WORKER = Path(__file__).with_name("enhance_worker.py")
_AUDIO_WORKER = Path(__file__).with_name("dereverb_worker.py")
_VIDEO_WORKER = Path(__file__).with_name("enhance_video_cpu.py")
_VIDEO_PYTHON = Path(os.getenv("SOVEREIGN_VIDEO_CPU_PYTHON", str(
    config.BASE_DIR / ".venv-matting" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))))
_AUDIO_PYTHON = Path(os.getenv("SOVEREIGN_DEREVERB_PYTHON", str(
    config.BASE_DIR / ".venv-audio-enhance" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))))


@lru_cache(maxsize=4)
def _audio_available(python: str) -> bool:
    if not Path(python).is_file():
        return False
    try:
        return subprocess.run([python, "-c", "import soundfile; from nara_wpe.utils import stft; from nara_wpe.wpe import wpe"],
                              capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


@lru_cache(maxsize=4)
def _video_available(python: str) -> bool:
    if not Path(python).is_file() or not find_ffmpeg_tool("ffmpeg"):
        return False
    try:
        return subprocess.run([python, "-c", "import cv2, numpy"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def kind_of(path: Path | str) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    raise EnhanceError("Unsupported media type.")


def _available(op: dict[str, Any]) -> tuple[bool, str]:
    engine = op["engine"]
    if engine == "cpu:video":
        ok = _video_available(str(_VIDEO_PYTHON))
        return ok, "" if ok else "Install OpenCV and NumPy in .venv-matting for CPU video finishing."
    if engine == "cpu:wpe":
        ok = _audio_available(str(_AUDIO_PYTHON))
        return ok, "" if ok else "Install requirements-enhance-audio.txt in .venv-audio-enhance for CPU speech cleanup."
    if engine == "ffmpeg":
        return (bool(find_ffmpeg_tool("ffmpeg")), "" if find_ffmpeg_tool("ffmpeg") else "FFmpeg is not installed.")
    if engine == "demucs":
        ok = Path(config.MUSIC_STEMS_PYTHON).is_file()
        return ok, "" if ok else "Demucs is not installed."
    name = engine.split(":", 1)[1]
    files = MODEL_FILES.get(name)
    if not files:
        return False, MODEL_HINTS.get(name, "Model not installed.")
    if not Path(config.MUSIC_STEMS_PYTHON).is_file():
        return False, "The GPU model environment (stems venv) is not installed."
    missing = [f.name for f in files if not f.is_file()]
    return (not missing), (MODEL_HINTS[name] + f" Missing: {', '.join(missing)}") if missing else ""


def catalog() -> list[dict[str, Any]]:
    out = []
    for op_id, op in OPERATIONS.items():
        ok, why = _available(op)
        out.append({"id": op_id, "label": op["label"], "kinds": op["kinds"], "engine": op["engine"],
                    "params": op["params"], "available": ok, "unavailable_reason": why or None})
    return out


def _params(op_id: str, given: dict[str, Any] | None) -> dict[str, float]:
    op = OPERATIONS[op_id]
    values = {}
    for p in op["params"]:
        raw = (given or {}).get(p["id"], p["default"])
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise EnhanceError(f"{op['label']}: {p['label']} must be a number.") from exc
        values[p["id"]] = min(max(value, p["min"]), p["max"])
    return values


def validate_ops(kind: str, ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not ops:
        raise EnhanceError("Choose at least one enhancement.")
    if len(ops) > MAX_OPS:
        raise EnhanceError(f"At most {MAX_OPS} enhancements at once.")
    clean = []
    for item in ops:
        op_id = item.get("op")
        op = OPERATIONS.get(op_id)
        if not op:
            raise EnhanceError(f"Unknown enhancement {op_id!r}.")
        if kind not in op["kinds"]:
            raise EnhanceError(f"{op['label']} does not apply to {kind}.")
        ok, why = _available(op)
        if not ok:
            raise EnhanceError(f"{op['label']}: {why}")
        clean.append({"op": op_id, "params": _params(op_id, item.get("params"))})
    if any(o["op"] == "separate" for o in clean) and len(clean) > 1:
        raise EnhanceError("Run vocal separation on its own; enhance the stems afterwards.")
    return clean


# --- ffmpeg graphs --------------------------------------------------------------------------

def video_filter(op: str, p: dict[str, float], kind: str = "video") -> str | None:
    if op == "denoise" and kind == "image":
        # Non-local means: a true spatial denoiser for a single frame (hqdn3d is mostly temporal).
        return f"nlmeans=s={2 + 10 * p['strength']:.1f}:p=7:r=15"
    if op == "denoise":
        s = p["strength"]
        return f"hqdn3d={1.5 + 6 * s:.2f}:{1.2 + 5 * s:.2f}:{2 + 8 * s:.2f}:{2 + 8 * s:.2f}"
    if op == "sharpen":
        return f"unsharp=5:5:{0.3 + 1.7 * p['amount']:.2f}:3:3:0.0"
    if op == "deblock":
        return "deblock=filter=strong:block=8"
    if op == "color":
        w = p["warmth"]
        return (f"eq=saturation={p['saturation']:.3f}:contrast={p['contrast']:.3f},"
                f"colorbalance=rs={0.08 * w:.3f}:bs={-0.08 * w:.3f}:rm={0.05 * w:.3f}:bm={-0.05 * w:.3f}")
    if op == "low_light":
        lift = p["lift"]
        return (f"eq=gamma={1 + 0.8 * lift:.3f}:brightness={0.04 * lift:.3f},"
                f"curves=all='0/0 0.25/{0.25 + 0.15 * lift:.3f} 1/1'")
    if op == "upscale_classic":
        return f"scale=-2:{int(p['target'])}:flags=lanczos"
    if op == "deflicker":
        return f"deflicker=size={int(p['window'])}:mode=am"
    if op == "interpolate":
        return f"minterpolate=fps={int(p['fps'])}:mi_mode=mci:mc_mode=aobmc:vsbmc=1"
    return None


def audio_filter(op: str, p: dict[str, float]) -> str | None:
    if op == "audio_denoise":
        return f"afftdn=nr={6 + 24 * p['strength']:.1f}:nf=-40:tn=1"
    if op == "vocal_clarity":
        g = p["presence"]
        return (f"highpass=f=80,equalizer=f=3000:t=q:w=1.2:g={2 + 4 * g:.1f},"
                f"equalizer=f=300:t=q:w=1:g={-1 - 2 * g:.1f},deesser=i={0.2 + 0.3 * g:.2f}")
    if op == "eq":
        return (f"bass=g={p['bass']:.1f}:f=100,equalizer=f=1000:t=q:w=1:g={p['mid']:.1f},"
                f"treble=g={p['treble']:.1f}:f=8000")
    if op == "stereo":
        return f"extrastereo=m={p['width']:.2f}"
    if op == "loudness":
        return f"loudnorm=I={p['lufs']:.0f}:TP=-1.0:LRA=11"
    if op == "master":
        d = p["drive"]
        return (f"acompressor=threshold={-12 - 10 * d:.1f}dB:ratio={1.5 + 2 * d:.2f}:attack=15:release=180:makeup={1 + 2 * d:.1f},"
                f"alimiter=limit=0.95:level=disabled")
    return None


def ffmpeg_args(src: Path, dst: Path, kind: str, ops: list[dict[str, Any]]) -> list[str]:
    vf = [f for o in ops if (f := video_filter(o["op"], o["params"], kind))]
    af = [f for o in ops if (f := audio_filter(o["op"], o["params"]))]
    args = ["-y", "-v", "error", "-nostats", "-progress", "pipe:1", "-i", str(src)]
    if kind == "image":
        args += ["-vf", ",".join(vf) or "null", "-frames:v", "1"]
        if dst.suffix.lower() in (".jpg", ".jpeg"):
            args += ["-q:v", "2"]
    elif kind == "audio":
        args += ["-af", ",".join(af) or "anull"]
        if dst.suffix.lower() == ".wav":
            args += ["-c:a", "pcm_s16le"]
    else:
        args += ["-vf", ",".join(vf) or "null", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                 "-pix_fmt", "yuv420p"]
        args += (["-af", ",".join(af)] if af else []) + ["-c:a", "aac", "-b:a", "256k"]
    return args + [str(dst)]


# --- Storage ------------------------------------------------------------------------------------

def _root() -> Path:
    path = STORAGE_DIR / "enhance"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _check(id_: str) -> str:
    if not _ID.match(id_ or ""):
        raise EnhanceError("Invalid id.")
    return id_


def _job_file(job_id: str) -> Path:
    return _root() / f"{_check(job_id)}.json"


def job_dir(job_id: str) -> Path:
    path = _root() / _check(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(job: dict[str, Any]) -> dict[str, Any]:
    job["updated_at"] = _now()
    with _lock:
        tmp = _job_file(job["id"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(job, indent=2), encoding="utf-8")
        tmp.replace(_job_file(job["id"]))
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    path = _job_file(job_id)
    if not path.exists():
        return None
    job = json.loads(path.read_text(encoding="utf-8"))
    if job["status"] in ("queued", "running") and job_id not in _procs and job_id not in _running:
        job.update(status="error", error="Interrupted by a restart. Run it again.")
    return job


def list_jobs(user_id: str) -> list[dict[str, Any]]:
    jobs = []
    for path in _root().glob("*.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if job.get("user_id") == user_id:
            jobs.append(get_job(job["id"]) or job)
    return sorted(jobs, key=lambda j: j["created_at"], reverse=True)


def delete_job(job_id: str) -> None:
    cancel(job_id)
    _job_file(job_id).unlink(missing_ok=True)
    shutil.rmtree(_root() / job_id, ignore_errors=True)


def resolve_storage_path(url_or_path: str) -> Path:
    """Accept a /storage/... URL of existing library media; never a path outside STORAGE_DIR."""
    rel = url_or_path.split("?", 1)[0]
    rel = rel[len("/storage/"):] if rel.startswith("/storage/") else rel
    path = (STORAGE_DIR / rel).resolve()
    if STORAGE_DIR.resolve() not in path.parents or not path.is_file():
        raise EnhanceError("Media not found in the library.")
    return path


def create_job(user_id: str, source: Path, name: str, ops: list[dict[str, Any]],
               job_id: str | None = None) -> dict[str, Any]:
    kind = kind_of(source)
    clean = validate_ops(kind, ops)
    job_id = job_id or uuid.uuid4().hex[:12]
    # Library media is referenced, not copied; uploads already live in their own job folder.
    job = {"id": job_id, "user_id": user_id, "kind": kind, "name": name[:200], "source": str(source),
           "ops": clean, "status": "queued", "progress": 0.0, "error": None, "outputs": [],
           "applied": None, "created_at": _now(), "updated_at": _now()}
    _save(job)
    _running.add(job_id)
    threading.Thread(target=_run, args=(job_id,), daemon=True, name=f"enhance-{job_id}").start()
    return job


def cancel(job_id: str) -> None:
    _cancelled.add(job_id)
    proc = _procs.get(job_id)
    if proc and proc.poll() is None:
        proc.terminate()


def _media_seconds(path: Path) -> float | None:
    return audio_duration(path)  # ffprobe format duration works for video and audio


def _run(job_id: str) -> None:
    import contextlib

    job = get_job(job_id)
    needs_gpu = any(OPERATIONS[op["op"]]["engine"].startswith("model:")
                    or OPERATIONS[op["op"]]["engine"] == "demucs" for op in job["ops"])
    # Remain queued while another production owns the GPU. Speech WPE and
    # FFmpeg filters do not need the card and must not wait behind a long film.
    with GPU_JOB_LOCK if needs_gpu else contextlib.nullcontext():
        _run_claimed(job_id)


def _run_claimed(job_id: str) -> None:
    job = get_job(job_id)
    try:
        if job_id in _cancelled:
            raise _Cancelled()
        job["status"] = "running"
        _save(job)
        source = Path(job["source"])
        folder = job_dir(job_id)
        if job["ops"][0]["op"] == "separate":
            outputs = _separate(job_id, source, folder)
        else:
            outputs = [_chain(job_id, source, folder, job["kind"], job["ops"])]
        job = get_job(job_id) or job
        job.update(status="done", progress=1.0, outputs=outputs)
    except _Cancelled:
        job.update(status="cancelled")
    except Exception as exc:  # noqa: BLE001 - reported on the job
        job.update(status="error", error=str(exc)[:500])
    finally:
        _procs.pop(job_id, None)
        _cancelled.discard(job_id)
        # Publish the terminal state before dropping the live-worker marker.
        # Pollers must not mistake this small completion window for a restart.
        try:
            _save(job)
        finally:
            _running.discard(job_id)


class _Cancelled(Exception):
    pass


def _passes(ops: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    passes: list[list[dict[str, Any]]] = []
    for o in ops:
        is_model = OPERATIONS[o["op"]]["engine"].startswith(("model:", "cpu:"))
        if passes and not is_model and not OPERATIONS[passes[-1][0]["op"]]["engine"].startswith(("model:", "cpu:")):
            passes[-1].append(o)
        else:
            passes.append([o])
    return passes


def _set_progress(job_id: str, value: float) -> None:
    job = get_job(job_id)
    if job:
        job["progress"] = round(min(0.99, value), 3)
        _save(job)


def _chain(job_id: str, source: Path, folder: Path, kind: str, ops: list[dict[str, Any]]) -> dict[str, Any]:
    ext = {"image": ".png", "audio": ".wav", "video": ".mp4"}[kind]
    if kind == "image" and source.suffix.lower() in (".jpg", ".jpeg"):
        ext = ".jpg"
    passes = _passes(ops)
    current = source
    for i, group in enumerate(passes):
        dst = folder / (f"enhanced{ext}" if i == len(passes) - 1 else f"step-{i}{ext}")
        span = (i / len(passes), (i + 1) / len(passes))
        if OPERATIONS[group[0]["op"]]["engine"].startswith(("model:", "cpu:")):
            _model(job_id, current, dst, group[0], span)
        else:
            _ffmpeg(job_id, current, dst, kind, group, span)
        if current != source:
            current.unlink(missing_ok=True)
        current = dst
    return {"label": "Enhanced", "path": str(current), "kind": kind}


def _model(job_id: str, src: Path, dst: Path, op: dict[str, Any], span: tuple[float, float]) -> None:
    python, worker = (_AUDIO_PYTHON, _AUDIO_WORKER) if op["op"] == "dereverb" else (config.MUSIC_STEMS_PYTHON, _WORKER)
    if op["op"] in {"motion_sharpen", "shot_match"}:
        python, worker = _VIDEO_PYTHON, _VIDEO_WORKER
    proc = subprocess.Popen([str(python), str(worker), op["op"], json.dumps(op["params"]), str(src), str(dst)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _procs[job_id] = proc
    for line in proc.stdout:
        if job_id in _cancelled:
            proc.terminate()
            break
        if line.startswith("PROGRESS "):
            try:
                _set_progress(job_id, span[0] + (span[1] - span[0]) * float(line.split()[1]))
            except ValueError:
                pass
    proc.wait(timeout=JOB_TIMEOUT)
    if job_id in _cancelled:
        dst.unlink(missing_ok=True)
        raise _Cancelled()
    if proc.returncode != 0 or not dst.is_file():
        err = [l for l in (proc.stderr.read() or "").splitlines() if l.strip() and "Warning" not in l]
        raise EnhanceError(f"{OPERATIONS[op['op']]['label']} failed: {(err or ['unknown error'])[-1][:300]}")


def _ffmpeg(job_id: str, source: Path, dst: Path, kind: str, ops: list[dict[str, Any]],
            span: tuple[float, float] = (0.0, 1.0)) -> None:
    ffmpeg = find_ffmpeg_tool("ffmpeg")
    total = _media_seconds(source) if kind != "image" else None
    proc = subprocess.Popen([ffmpeg, *ffmpeg_args(source, dst, kind, ops)], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    _procs[job_id] = proc
    last = 0.0
    for line in proc.stdout:  # -progress key=value lines
        if job_id in _cancelled:
            proc.terminate()
            break
        if total and line.startswith("out_time_us="):
            try:
                done = int(line.split("=", 1)[1]) / 1e6
            except ValueError:
                continue
            frac = span[0] + (span[1] - span[0]) * min(1.0, done / total)
            if frac - last >= 0.02:
                last = frac
                _set_progress(job_id, frac)
    proc.wait(timeout=JOB_TIMEOUT)
    if job_id in _cancelled:
        dst.unlink(missing_ok=True)
        raise _Cancelled()
    if proc.returncode != 0 or not dst.is_file():
        raise EnhanceError(f"Enhancement failed: {(proc.stderr.read() or '').strip()[-300:]}")


def _separate(job_id: str, source: Path, folder: Path) -> list[dict[str, Any]]:
    worker = Path(__file__).with_name("stems_worker.py")
    out = folder / "stems"
    proc = subprocess.Popen([config.MUSIC_STEMS_PYTHON, str(worker), str(source), str(out)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _procs[job_id] = proc
    _, err = proc.communicate(timeout=JOB_TIMEOUT)
    if job_id in _cancelled:
        raise _Cancelled()
    if proc.returncode != 0:
        raise EnhanceError(f"Separation failed: {(err.strip().splitlines() or ['unknown error'])[-1][:300]}")
    return [{"label": "Vocals", "path": str(out / "vocals.wav"), "kind": "audio"},
            {"label": "Instrumental", "path": str(out / "instrumental.wav"), "kind": "audio"}]


def apply(job_id: str, output_index: int = 0) -> dict[str, Any]:
    """Mark a version as the one to use. The original is kept untouched (non-destructive)."""
    job = get_job(job_id)
    if job is None or job["status"] != "done":
        raise EnhanceError("Only a finished enhancement can be applied.")
    if not 0 <= output_index < len(job["outputs"]):
        raise EnhanceError("Unknown output.")
    job["applied"] = {"index": output_index, "at": _now()}
    return _save(job)


# --- Presets ------------------------------------------------------------------------------------

def _presets_file(user_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", user_id)[:64]
    return _root() / f"presets-{safe}.json"


def list_presets(user_id: str) -> list[dict[str, Any]]:
    path = _presets_file(user_id)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def save_preset(user_id: str, name: str, kind: str, ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if kind not in ("image", "audio", "video"):
        raise EnhanceError("Unknown media kind.")
    clean = []
    for item in ops:  # presets may include ops whose model is not installed yet
        if item.get("op") not in OPERATIONS or kind not in OPERATIONS[item["op"]]["kinds"]:
            raise EnhanceError(f"Unknown enhancement {item.get('op')!r} for {kind}.")
        clean.append({"op": item["op"], "params": _params(item["op"], item.get("params"))})
    name = name.strip()[:60]
    if not name or not clean:
        raise EnhanceError("A preset needs a name and at least one enhancement.")
    presets = [p for p in list_presets(user_id) if not (p["name"] == name and p["kind"] == kind)]
    presets.append({"id": uuid.uuid4().hex[:10], "name": name, "kind": kind, "ops": clean})
    _presets_file(user_id).write_text(json.dumps(presets, indent=2), encoding="utf-8")
    return presets


def delete_preset(user_id: str, preset_id: str) -> list[dict[str, Any]]:
    presets = [p for p in list_presets(user_id) if p["id"] != preset_id]
    _presets_file(user_id).write_text(json.dumps(presets, indent=2), encoding="utf-8")
    return presets
