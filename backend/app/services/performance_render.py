"""Render a Multi-Performer Director project to video (local ComfyUI, Wan 2.1 + InfiniteTalk).

Shared-pass mode uses one two-speaker InfiniteTalk generation with separate masked audio.
Independent-layer mode generates each performer separately, caches complete passes and
composites transparent performer layers onto one stage. Mask edges and model behavior require visual review.

Long songs are rendered as overlapping chunks (the avatar renderer's proven extension scheme),
joined, re-framed per camera shot (close-up / two-shot / wide as digital crops of the master
shot), and muxed with the untouched master song.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import subprocess
import math
import os
import shutil
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .. import config
from . import performance_engine as pe
from .gpu_jobs import GPU_JOB_LOCK
from .avatar_comfyui import (FPS, MOTION_FRAMES, _find_video, _join_chunks, _run_ffmpeg, _slice_audio,
                             _upload, plan_chunks)

WIDTH, HEIGHT = int(os.getenv("PERFORMANCE_WIDTH", "832")), int(os.getenv("PERFORMANCE_HEIGHT", "480"))
CHUNK_FRAMES = int(os.getenv("PERFORMANCE_CHUNK_FRAMES", "81"))
INITIAL_HOLD_FRAMES = max(0, int(os.getenv("PERFORMANCE_INITIAL_HOLD_FRAMES", "4")))
STEPS = int(os.getenv("PERFORMANCE_STEPS", "4"))
CFG = float(os.getenv("PERFORMANCE_CFG", "1.0"))
MULTI_PATCH = os.getenv("PERFORMANCE_MULTI_PATCH", "infinitetalk_multi.safetensors")
UPSCALE = int(os.getenv("PERFORMANCE_UPSCALE", "2"))
# InfiniteTalk audio conditioning strength. Distilled 4-step sampling with cfg 1 under-articulates singing
# at 1.0, especially on faces turned away from the camera.
AUDIO_SCALE = float(os.getenv("PERFORMANCE_AUDIO_SCALE", "1.0"))
PARALLEL_NODE = "SovereignInfiniteTalkParallel"
SPEED_LORA = os.getenv("PERFORMANCE_LORA", "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors")
CHUNK_TIMEOUT = 1800
POLL = 3.0
NEGATIVE = ("low quality, blurry, flicker, distorted mouth, warped face, face swap, identity change, "
            "duplicated person, mirrored movement, extra limbs, watermark, text")

_active: set[str] = set()
_cancelled: set[str] = set()
_gpu = GPU_JOB_LOCK


class Cancelled(Exception):
    pass


# --- Stage picture and speaker masks --------------------------------------------------------

def _bounds(project: dict[str, Any]) -> list[tuple[float, float]]:
    """Each performer's horizontal slice of the frame: from the midpoint to their neighbours."""
    xs = [p["stage"]["x"] for p in project["performers"]]
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    bounds: list[tuple[float, float]] = [(0.0, 1.0)] * len(xs)
    for rank, i in enumerate(order):
        left = 0.0 if rank == 0 else (xs[order[rank - 1]] + xs[i]) / 2
        right = 1.0 if rank == len(order) - 1 else (xs[i] + xs[order[rank + 1]]) / 2
        bounds[i] = (left, right)
    return bounds


def compose_stage(project: dict[str, Any], out: Path, *, background_only: bool = False) -> Path:
    """The first frame: the stage picture if given (already showing everyone), else each identity
    picture contained in its own slice of a dark concert-stage backdrop."""
    from PIL import Image, ImageDraw, ImageFilter, ImageOps

    stage_image = project.get("stage", {}).get("image")
    # The reference stage image may already contain both singers. Never duplicate them
    # behind independently extracted performers; use the empty generated backdrop instead.
    if not background_only and stage_image and Path(stage_image).is_file():
        with Image.open(stage_image) as raw:
            frame = ImageOps.fit(ImageOps.exif_transpose(raw).convert("RGB"), (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
        frame.save(out, "PNG")
        return out
    frame = Image.new("RGB", (WIDTH, HEIGHT), (14, 12, 22))
    glow = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(glow)
    for p, (left, right) in zip(project["performers"], _bounds(project)):
        cx = p["stage"]["x"] * WIDTH
        draw.ellipse([cx - WIDTH * 0.18, -HEIGHT * 0.2, cx + WIDTH * 0.18, HEIGHT * 1.1], fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(60))
    frame = Image.composite(Image.new("RGB", frame.size, (90, 70, 130)), frame, glow)
    if background_only:
        frame.save(out, "PNG")
        return out
    for p, (left, right) in zip(project["performers"], _bounds(project)):
        if not p.get("identity_image"):
            raise pe.PerformanceError(f"{p['name']} needs an identity picture.")
        slot_w = int((right - left) * WIDTH * 0.92 * p["stage"].get("scale", 1.0))
        slot_h = int(HEIGHT * project.get("portrait_height", 0.96) * p["stage"].get("scale", 1.0))
        with Image.open(p["identity_image"]) as raw:
            person = ImageOps.contain(ImageOps.exif_transpose(raw).convert("RGBA"), (slot_w, slot_h),
                                      Image.Resampling.LANCZOS)
        x = int(p["stage"]["x"] * WIDTH - person.width / 2)
        x = max(int(left * WIDTH), min(x, int(right * WIDTH) - person.width))
        frame.paste(person, (x, HEIGHT - person.height), person.getchannel("A"))
    frame.save(out, "PNG")
    return out


def speaker_masks(project: dict[str, Any], folder: Path) -> list[Path]:
    from PIL import Image

    paths = []
    for i, (left, right) in enumerate(_bounds(project)):
        mask = Image.new("L", (WIDTH, HEIGHT), 0)
        mask.paste(255, (int(left * WIDTH), 0, int(right * WIDTH), HEIGHT))
        path = folder / f"mask-{i}.png"
        mask.save(path)
        paths.append(path)
    return paths


# --- Workflow --------------------------------------------------------------------------------

def _visible_chunk_window(plan, duration: float) -> tuple[float, float]:
    """Song time actually retained after InfiniteTalk's extension context is trimmed."""
    # An extension's audio file starts at the PREVIOUS chunk's origin. The node
    # skips previous_length-motion frames, and joining drops motion more frames.
    start = (plan.audio_start_frame + (CHUNK_FRAMES if plan.extends else 0)) / FPS
    frames = plan.length - (MOTION_FRAMES if plan.extends else 0)
    return start, min(duration, start + frames / FPS)


def _prompt_for(project: dict[str, Any], start: float, end: float) -> str:
    """Stage directions for this window, in screen order (left to right)."""
    mid = (start + end) / 2
    parts = []
    side = {0: "on the left", 1: "on the right"} if len(project["performers"]) == 2 else {0: ""}
    order = sorted(project["performers"], key=lambda p: p["stage"]["x"])
    for rank, p in enumerate(order):
        cue = next((c for c in pe.motion_cues(project, p["id"]) if c["start"] <= mid < c["end"]), None)
        parts.append(f"the performer {side.get(rank, '')} {cue['direction'] if cue else 'stands naturally'}".replace("  ", " "))
    scene = project.get("stage", {}).get("prompt") or "a professional concert stage with consistent stage lighting"
    who = "Two adult singers" if len(order) == 2 else "An adult singer"
    return f"{who} on {scene}, live performance, smooth camera. " + "; ".join(parts) + \
        ". Each person moves independently, consistent identity, accurate lip sync."


def build_workflow(*, image: str, audios: list[str], masks: list[str], prompt: str, seed: int, length: int,
                   prev_video: str | None = None) -> dict[str, Any]:
    two = len(audios) == 2
    wf: dict[str, Any] = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": config.AVATAR_WAN_MODEL_NAME, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": NEGATIVE}},
        "13": {"class_type": "AudioEncoderLoader", "inputs": {"audio_encoder_name": config.AVATAR_AUDIO_ENCODER_NAME}},
        "15": {"class_type": "ModelPatchLoader",
               "inputs": {"name": MULTI_PATCH if two else config.AVATAR_INFINITETALK_PATCH_NAME}},
        "12": {"class_type": "LoadAudio", "inputs": {"audio": audios[0]}},
        "14": {"class_type": "AudioEncoderEncode", "inputs": {"audio_encoder": ["13", 0], "audio": ["12", 0]}},
    }
    model: list[Any] = ["1", 0]
    if SPEED_LORA:
        wf["16"] = {"class_type": "LoraLoaderModelOnly",
                    "inputs": {"model": model, "lora_name": SPEED_LORA, "strength_model": 1.0}}
        model = ["16", 0]
    talk: dict[str, Any] = {
        "mode": "single_speaker", "model": model, "model_patch": ["15", 0], "positive": ["5", 0],
        "negative": ["6", 0], "vae": ["3", 0], "width": WIDTH, "height": HEIGHT, "length": length,
        "audio_encoder_output_1": ["14", 0], "motion_frame_count": MOTION_FRAMES, "audio_scale": AUDIO_SCALE,
        "start_image": ["4", 0],
    }
    if two:
        wf["22"] = {"class_type": "LoadAudio", "inputs": {"audio": audios[1]}}
        wf["24"] = {"class_type": "AudioEncoderEncode", "inputs": {"audio_encoder": ["13", 0], "audio": ["22", 0]}}
        wf["30"] = {"class_type": "LoadImageMask", "inputs": {"image": masks[0], "channel": "red"}}
        wf["31"] = {"class_type": "LoadImageMask", "inputs": {"image": masks[1], "channel": "red"}}
        talk.update({"mode": "two_speakers", "mode.audio_encoder_output_2": ["24", 0],
                     "mode.mask_1": ["30", 0], "mode.mask_2": ["31", 0]})
    if prev_video:
        wf["90"] = {"class_type": "LoadVideo", "inputs": {"file": prev_video}}
        wf["91"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["90", 0]}}
        talk["previous_frames"] = ["91", 0]
    # Two performers: Sovereign's parallel-voices node (both tracks on the song's timeline; the stock node
    # lays speaker 2 after speaker 1). tools/comfyui_nodes/sovereign_infinitetalk_parallel.py
    wf["7"] = {"class_type": PARALLEL_NODE if two else "WanInfiniteTalkToVideo", "inputs": talk}
    wf["8"] = {"class_type": "KSampler", "inputs": {
        "model": ["7", 0], "seed": seed, "steps": STEPS, "cfg": CFG, "sampler_name": "euler",
        "scheduler": "simple", "positive": ["7", 1], "negative": ["7", 2], "latent_image": ["7", 3], "denoise": 1.0}}
    wf["9"] = {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}}
    wf["10"] = {"class_type": "CreateVideo", "inputs": {"images": ["9", 0], "audio": ["12", 0], "fps": FPS}}
    wf["11"] = {"class_type": "SaveVideo", "inputs": {"video": ["10", 0], "filename_prefix": "sovereign_performance",
                                                       "format": "mp4", "codec": "h264"}}
    return wf


# --- Camera reframe ----------------------------------------------------------------------------

def crop_for(project: dict[str, Any], shot: dict[str, Any] | None) -> tuple[int, int, int, int]:
    """(w, h, x, y) crop of the master frame for a camera shot. Even sizes for x264."""
    if not shot or shot["shot"] in ("wide", "alternating"):
        return WIDTH, HEIGHT, 0, 0
    zoom = 0.82 if shot["shot"] == "two_shot" else 0.55
    w, h = int(WIDTH * zoom) // 2 * 2, int(HEIGHT * zoom) // 2 * 2
    cx = WIDTH / 2
    if shot["shot"] == "close_up" and shot.get("focus"):
        cx = pe.performer(project, shot["focus"])["stage"]["x"] * WIDTH
    x = int(min(max(cx - w / 2, 0), WIDTH - w))
    y = int(max(0, HEIGHT * 0.06)) if shot["shot"] == "close_up" else (HEIGHT - h) // 2
    return w, h, x, min(y, HEIGHT - h)


def reframe(project: dict[str, Any], master_video: Path, out: Path) -> Path:
    shots = project.get("camera") or []
    if not shots or all(crop_for(project, s) == (WIDTH, HEIGHT, 0, 0) for s in shots):
        shutil.copyfile(master_video, out)
        return out
    parts, labels = [], []
    for i, s in enumerate(shots):
        w, h, x, y = crop_for(project, s)
        parts.append(f"[0:v]trim=start={s['start']:.3f}:end={s['end']:.3f},setpts=PTS-STARTPTS,"
                     f"crop={w}:{h}:{x}:{y},scale={WIDTH}:{HEIGHT}:flags=lanczos,setsar=1[c{i}]")
        labels.append(f"[c{i}]")
    graph = ";".join(parts) + f";{''.join(labels)}concat=n={len(shots)}:v=1:a=0[v]"
    _run_ffmpeg(["-i", str(master_video), "-filter_complex", graph, "-map", "[v]", "-c:v", "libx264", "-crf", "18",
                 "-pix_fmt", "yuv420p", "-an", str(out)])
    return out


# --- Job ---------------------------------------------------------------------------------------

def _status(project_id: str, **fields: Any) -> None:
    project = pe.get(project_id)
    if project is None:
        return
    render = project.get("render") or {}
    render.update(fields, updated_at=datetime.now(timezone.utc).isoformat())
    project["render"] = render
    pe.save(project)


def readiness() -> list[str]:
    """Files the renderer needs that are missing (checked against ComfyUI's model folders)."""
    root = Path(os.getenv("COMFYUI_MODELS_DIR", "/mnt/storage/AI-Models/comfyui"))
    needed = {"model_patches": [MULTI_PATCH], "diffusion_models": [config.AVATAR_WAN_MODEL_NAME],
              "audio_encoders": [config.AVATAR_AUDIO_ENCODER_NAME], "vae": ["wan_2.1_vae.safetensors"],
              "text_encoders": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"]}
    if SPEED_LORA:
        needed["loras"] = [SPEED_LORA]
    if not root.is_dir():
        return []  # models live elsewhere (e.g. a Windows install); ComfyUI will report anything missing
    return [f"{folder}/{name}" for folder, names in needed.items() for name in names
            if not (root / folder / name).is_file()]


def start(project_id: str) -> dict[str, Any]:
    project = pe.get(project_id)
    if project is None:
        raise pe.PerformanceError("Performance not found.")
    if project_id in _active:
        raise pe.PerformanceError("This performance is already rendering.")
    for performer in project["performers"]:
        from . import performance_reference as reference
        pending = reference.pending_status(performer) or {}
        if pending.get("status") == "processing":
            raise pe.PerformanceError("Wait for reference preparation to finish.")
        if pending.get("status") == "error" and not performer.get("reference"):
            raise pe.PerformanceError("Reference preparation failed. Retry or detach the reference.")
        if performer.get("reference"):
            from . import performance_reference as reference
            if project.get("render_strategy") != "independent_layers":
                raise pe.PerformanceError("Reference motion requires independent performer layers.")
            if (reference.pending_status(performer) or {}).get("status") == "processing":
                raise pe.PerformanceError("Wait for reference preparation to finish.")
            if performer["reference"]["duration"] + .001 < project["duration"]:
                raise pe.PerformanceError("Reference video must cover the whole performance timeline.")
            root = Path(os.getenv("COMFYUI_MODELS_DIR", "/mnt/storage/AI-Models/comfyui"))
            if not reference.python().is_file() or not (root / "diffusion_models" / reference.MODEL).is_file() or not (root / "clip_vision" / reference.VISION).is_file():
                raise pe.PerformanceError("Install the reference motion model, vision model and isolated CPU pose environment.")
    plan = pe.render_plan(project)
    if not plan["ready"]:
        raise pe.PerformanceError("Still missing: " + ", ".join(plan["missing"]) + ".")
    if len(project["performers"]) > 2 and project.get("render_strategy") != "independent_layers":
        raise pe.PerformanceError("Rendering more than two performers is not built yet (planned: paired passes "
                                  "composited on the shared stage).")
    missing = readiness()
    if project.get("render_strategy") == "independent_layers" or len(project["performers"]) == 1:
        missing = [name for name in missing if name != f"model_patches/{MULTI_PATCH}"]
        root = Path(os.getenv("COMFYUI_MODELS_DIR", "/mnt/storage/AI-Models/comfyui"))
        single = f"model_patches/{config.AVATAR_INFINITETALK_PATCH_NAME}"
        if root.is_dir() and not (root / single).is_file():
            missing.append(single)
    if missing:
        raise pe.PerformanceError("Model files missing: " + ", ".join(missing) + ".")
    if project.get("render_strategy") == "independent_layers":
        python, model_dir = _matting_paths()
        if not Path(python).is_file() or not (model_dir / "u2net_human_seg.onnx").is_file():
            raise pe.PerformanceError("Independent rendering requires the CPU matting environment and U2Net human model.")
    pe.validate(project)
    _active.add(project_id)
    _cancelled.discard(project_id)
    _status(project_id, status="queued", stage="Waiting for the GPU", progress=0.0, error=None, video=None)
    threading.Thread(target=_run, args=(project_id,), daemon=True, name=f"performance-{project_id}").start()
    return pe.get(project_id)


def cancel(project_id: str) -> None:
    if project_id in _active:
        _cancelled.add(project_id)


def _run(project_id: str) -> None:
    try:
        with _gpu:
            asyncio.run(_render(project_id))
    except Cancelled:
        _status(project_id, status="cancelled", stage="Cancelled")
    except Exception as exc:  # noqa: BLE001 - every failure is reported on the project, never faked
        _status(project_id, status="error", stage="Failed", error=str(exc)[:500])
    finally:
        _active.discard(project_id)
        _cancelled.discard(project_id)


async def _render(project_id: str) -> None:
    project = pe.get(project_id)
    for p in project["performers"]:
        pe.build_drive_audio(project, p["id"])
    pe.save(project)
    folder = pe.media_dir(project_id)
    work = Path(tempfile.mkdtemp(prefix="performance_"))
    tag = uuid.uuid4().hex[:8]
    try:
        if project.get("render_strategy") == "independent_layers":
            await _render_layers(project, folder, work, tag)
            return
        stage = compose_stage(project, work / f"{tag}-stage.png")
        shutil.copyfile(stage, folder / "stage-frame.png")
        masks = speaker_masks(project, work) if len(project["performers"]) == 2 else []
        drives = [Path(p["drive_audio"]) for p in project["performers"]]
        plans, total_frames = plan_chunks(project["duration"], CHUNK_FRAMES)
        seed = sum(p["motion"]["seed"] for p in project["performers"]) % 2**31
        async with httpx.AsyncClient(base_url=config.COMFYUI_BASE_URL.rstrip("/"), timeout=60.0) as client:
            image = await _upload(client, stage, "image")
            mask_names = [await _upload(client, m, "image") for m in masks]
            chunks: list[Path] = []
            for i, plan in enumerate(plans):
                if project_id in _cancelled:
                    raise Cancelled()
                _status(project_id, status="running", progress=round(i / len(plans), 3),
                        stage=f"Performing part {i + 1} of {len(plans)}")
                audio_names = []
                for k, drive in enumerate(drives):
                    piece = work / f"{tag}-a{k}-{i}.wav"
                    _slice_audio(drive, plan, piece)
                    audio_names.append(await _upload(client, piece, "audio"))
                window_start, window_end = _visible_chunk_window(plan, project["duration"])
                prompt = _prompt_for(project, window_start, window_end)
                prev = await _upload(client, chunks[-1], "video") if plan.extends else None
                wf = build_workflow(image=image, audios=audio_names, masks=mask_names, prompt=prompt,
                                    seed=seed + i, length=plan.length, prev_video=prev)
                chunk = work / f"{tag}-v{i}.mp4"
                await _submit(client, wf, chunk, project_id)
                chunks.append(chunk)
        _status(project_id, stage="Joining, framing and mixing", progress=0.97)
        joined = work / f"{tag}-joined.mp4"
        _join_chunks(chunks, Path(project["master_audio"]), total_frames, joined)
        joined = _align_visual_timing(project, joined, work / f"{tag}-aligned.mp4")
        master_shot = folder / "master-shot.mp4"
        shutil.copyfile(joined, master_shot)
        framed = reframe(project, joined, work / f"{tag}-framed.mp4")
        final = folder / "performance.mp4"
        _run_ffmpeg(["-i", str(framed), "-i", str(project["master_audio"]), "-map", "0:v", "-map", "1:a",
                     "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", str(final)])
        hd = _upscale(project_id, final, folder / "performance-hd.mp4")
        _status(project_id, stage="Encoding browser preview", progress=.99)
        _browser_preview(hd or final, folder)
        _status(project_id, status="done", stage="Done", progress=1.0, video=str(hd or final),
                video_sd=str(final), master_shot=str(master_shot), chunks=len(plans),
                upscaled=bool(hd), visual_delay_ms=round(float(project.get("visual_delay_ms", 0)) * FPS / 1000) * 1000 / FPS)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _layer_key(project: dict[str, Any], p: dict[str, Any]) -> str:
    """Hash actual inputs and effective generation settings; camera edits reuse performances."""
    digest = hashlib.sha256()
    settings = {"version": 3, "width": WIDTH, "height": HEIGHT, "fps": FPS,
                "chunk": CHUNK_FRAMES, "steps": STEPS, "cfg": CFG, "audio_scale": AUDIO_SCALE,
                "model": config.AVATAR_WAN_MODEL_NAME, "patch": config.AVATAR_INFINITETALK_PATCH_NAME,
                "encoder": config.AVATAR_AUDIO_ENCODER_NAME, "lora": SPEED_LORA, "negative": NEGATIVE,
                "duration": project["duration"], "motion": p["motion"], "scale": p["stage"].get("scale", 1),
                "cues": pe.motion_cues(project, p["id"]), "scene": project.get("stage", {}).get("prompt")}
    digest.update(json.dumps(settings, sort_keys=True).encode())
    for name in ("identity_image", "drive_audio"):
        with Path(p[name]).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def compose_layers(project: dict[str, Any], layers: list[Path], background: Path, out: Path) -> Path:
    """Overlay full alpha layers; never paste independently generated backgrounds or zone edges."""
    args = ["-loop", "1", "-i", str(background)]
    for layer in layers:
        args += ["-i", str(layer)]
    args += ["-i", str(project["master_audio"])]
    graph = [f"[0:v]fps={FPS},format=yuv420p,setsar=1[base]"]
    previous = "base"
    for i, person in enumerate(project["performers"]):
        x = round((person["stage"]["x"] - .5) * WIDTH)
        # InfiniteTalk's conditioning latent can posterize its opening frames. Hold
        # the first stable frame in place; preserve all later timestamps and audio.
        hold = min(INITIAL_HOLD_FRAMES, max(0, math.ceil(project["duration"] * FPS)-1)) if not person.get("reference") else 0
        opening = f",trim=start_frame={hold},setpts=PTS-STARTPTS,tpad=start={hold}:start_mode=clone" if hold else ""
        graph.append(f"[{i + 1}:v]scale={WIDTH}:{HEIGHT}:flags=lanczos,format=rgba,setsar=1{opening}[p{i}]")
        graph.append(f"[{previous}][p{i}]overlay={x}:0:shortest=1:format=auto[v{i}]")
        previous = f"v{i}"
    _run_ffmpeg(args + ["-filter_complex", ";".join(graph), "-map", f"[{previous}]",
                       "-map", f"{len(layers)+1}:a", "-t", str(project["duration"]),
                       "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-b:a", "256k", str(out)])
    return out


def _align_visual_timing(project: dict[str, Any], source: Path, target: Path) -> Path:
    """Shift only pictures by whole frames; keep source audio and total duration."""
    frames = round(float(project.get("visual_delay_ms", 0)) * FPS / 1000)
    if not frames:
        return source
    duration = project["duration"]
    total = round(duration * FPS)
    if frames > 0:
        filters = f"tpad=start_mode=clone:start_duration={frames / FPS},trim=end_frame={total},setpts=PTS-STARTPTS"
    else:
        filters = (f"trim=start_frame={-frames},setpts=PTS-STARTPTS,"
                   f"tpad=stop_mode=clone:stop_duration={-frames / FPS},trim=end_frame={total}")
    _run_ffmpeg(["-i", str(source), "-vf", filters, "-c:v", "libx264", "-crf", "18",
                 "-pix_fmt", "yuv420p", "-c:a", "copy", "-t", str(duration), str(target)])
    return target


def _matting_paths() -> tuple[str, Path]:
    executable = config.BASE_DIR / ".venv-matting" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return (os.getenv("PERFORMANCE_MATTING_PYTHON", str(executable)),
            Path(os.getenv("PERFORMANCE_MATTING_MODELS", "/mnt/storage/AI-Models/matting")))


def _matte_layer(source: Path, target: Path) -> Path:
    """Publish only a complete lossless alpha pass; cache it independently of composition."""
    import subprocess

    python, model_dir = _matting_paths()
    if not Path(python).is_file() or not (model_dir / "u2net_human_seg.onnx").is_file():
        raise pe.PerformanceError("Independent rendering requires the CPU matting environment and U2Net human model.")
    temporary = target.with_name(target.stem + ".partial" + target.suffix)
    env = dict(os.environ, U2NET_HOME=str(model_dir), OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2")
    result = subprocess.run([python, str(Path(__file__).with_name("performance_matte_worker.py")),
                             str(source), str(temporary)], env=env, capture_output=True, text=True,
                            timeout=6 * 3600)
    if result.returncode or not temporary.is_file():
        raise pe.PerformanceError("Performer extraction failed: " + result.stderr[-1500:])
    temporary.replace(target)
    return target


async def _transfer_reference(project, performer, original, base_key, client, work, tag):
    from . import performance_reference as reference
    ref = performer["reference"]
    if (reference.pending_status(performer) or {}).get("status") == "processing":
        raise pe.PerformanceError("Wait for reference preparation to finish.")
    if ref["duration"] + .001 < project["duration"]:
        raise pe.PerformanceError("Reference video must cover the whole performance timeline.")
    key = reference.transfer_key(base_key, ref)
    folder = original.parent / (performer["id"] + "-reference-" + key)
    folder.mkdir(exist_ok=True)
    target = folder / "transferred.mp4"
    if target.is_file() and (folder / "mask.mp4").is_file():
        return target, key, folder / "mask.mp4", True
    edits = folder / "edits.json"
    edits.write_text(json.dumps(ref["edits"]))
    _status(project["id"], stage=f"Preparing {performer['name']}'s measured motion and own-vocal face (CPU)")
    await asyncio.to_thread(reference.worker, "guide", ref["tracks"], edits, original, folder)
    # Always use the original portrait, not a generated frame containing inherited artifacts.
    identity = folder / "identity-alpha.png"
    await asyncio.to_thread(_matte_layer, Path(performer["identity_image"]), identity)
    from PIL import Image
    with Image.open(identity) as image:
        image = image.convert("RGBA")
        image.thumbnail((340, 330), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (640, 368), (18, 14, 30, 255))
        canvas.alpha_composite(image, ((640-image.width)//2, 368-image.height))
        canvas.convert("RGB").save(folder / "reference-identity.png")
    uploaded_identity = await _upload(client, folder / "reference-identity.png", "image")
    total = math.ceil(project["duration"] * FPS)
    done, chunks = 0, []
    while done < total:
        if project["id"] in _cancelled:
            raise Cancelled()
        overlap = 5 if chunks else 0
        wanted = min(52 if chunks else 53, total-done)
        length = 4 * math.ceil((wanted+overlap-1)/4) + 1
        start = done-overlap
        names = {}
        for name in ("pose", "face", "background", "mask"):
            piece = folder / f"{name}-{len(chunks)}.mp4"
            await asyncio.to_thread(_run_ffmpeg, ["-ss", str(start/FPS), "-i", str(folder / (name+".mp4")),
                "-vf", f"tpad=stop_mode=clone:stop_duration={length/FPS}", "-frames:v", str(length),
                "-an", "-c:v", "libx264", "-threads", "2", "-crf", "15", str(piece)])
            names[name] = await _upload(client, piece, "video")
        audio = folder / f"audio-{len(chunks)}.wav"
        await asyncio.to_thread(_run_ffmpeg, ["-ss", str(done/FPS), "-i", performer["drive_audio"],
            "-af", "apad", "-t", str((length-overlap)/FPS), str(audio)])
        previous = await _upload(client, chunks[-1], "video") if chunks else None
        graph = reference.workflow(identity=uploaded_identity, **names, audio=await _upload(client, audio, "audio"),
            seed=performer["motion"]["seed"]+len(chunks), length=length, previous=previous)
        chunk = folder / f"chunk-{len(chunks)}.mp4"
        _status(project["id"], stage=f"Transferring {performer['name']}'s measured motion: {done/FPS:.1f}s")
        await _submit(client, graph, chunk, project["id"])
        chunks.append(chunk)
        done += length-overlap
    listing = folder / "concat.txt"
    listing.write_text("\n".join("file '"+str(c.resolve()).replace("'", "'\\''")+"'" for c in chunks)+"\n")
    pending = folder / "transfer-pending.mp4"
    await asyncio.to_thread(_run_ffmpeg, ["-f", "concat", "-safe", "0", "-i", str(listing),
        "-i", performer["drive_audio"], "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "-1",
        "-c:v", "libx264", "-threads", "2", "-crf", "17", "-c:a", "aac", "-frames:v", str(total),
        "-t", str(total/FPS), str(pending)])
    pending.replace(target)
    return target, key, folder / "mask.mp4", False


def _recover_reference_alpha(source, alpha, mask):
    from . import performance_reference as reference
    pending = alpha.with_name(alpha.stem+"-recovering.mkv")
    try:
        subprocess.run([str(reference.python()), str(Path(__file__).with_name("performance_background_alpha_worker.py")),
                        str(source), str(alpha), str(mask), str(pending)], check=True, capture_output=True, timeout=7200)
        pending.replace(alpha)
    except Exception:
        pending.unlink(missing_ok=True)
        alpha.unlink(missing_ok=True)  # Never cache an incomplete reference extraction.
        raise


async def _render_layers(project: dict[str, Any], folder: Path, work: Path, tag: str) -> None:
    project_id = project["id"]
    plans, total_frames = plan_chunks(project["duration"], CHUNK_FRAMES)
    cache = folder / "layers"
    cache.mkdir(exist_ok=True)
    layers, manifest = [], []
    async with httpx.AsyncClient(base_url=config.COMFYUI_BASE_URL.rstrip("/"), timeout=60.0) as client:
        for index, p in enumerate(project["performers"]):
            if project_id in _cancelled:
                raise Cancelled()
            key = _layer_key(project, p)
            target = cache / f"{p['id']}-{key}.mp4"
            reused = target.is_file() and target.stat().st_size > 0
            if not reused:
                solo = copy.deepcopy(project)
                solo["performers"] = [copy.deepcopy(p)]
                solo["performers"][0]["stage"]["x"] = 0.5
                # A shared stage photograph may contain the other singer: never feed that
                # into a single-person pass and accidentally duplicate their identity.
                solo["stage"]["image"] = None
                solo["portrait_height"] = .88  # leave room above the hair for generated motion
                identity = work / f"{tag}-{p['id']}-identity.png"
                _status(project_id, stage=f"Preparing {p['name']}'s transparent identity (CPU)")
                await asyncio.to_thread(_matte_layer, Path(p["identity_image"]), identity)
                solo["performers"][0]["identity_image"] = str(identity)
                image = compose_stage(solo, work / f"{tag}-{p['id']}.png")
                uploaded = await _upload(client, image, "image")
                cues = pe.motion_cues(project, p["id"])
                chunks = []
                for i, plan in enumerate(plans):
                    if project_id in _cancelled:
                        raise Cancelled()
                    progress = (index + i / len(plans)) / len(project["performers"])
                    _status(project_id, status="running", progress=round(progress * .94, 3),
                            stage=f"{p['name']}: part {i+1} of {len(plans)}")
                    piece = work / f"{tag}-{p['id']}-{i}.wav"
                    _slice_audio(Path(p["drive_audio"]), plan, piece)
                    audio = await _upload(client, piece, "audio")
                    window_start, window_end = _visible_chunk_window(plan, project["duration"])
                    mid = (window_start + window_end) / 2
                    cue = next((c for c in cues if c["start"] <= mid < c["end"]), None)
                    prompt = (f"One adult performer on {project['stage'].get('prompt') or 'a concert stage'}, "
                              f"{cue['direction'] if cue else 'stands naturally'}, consistent identity, accurate lip sync, "
                              "entire head visible with space above the hair, no frame borders")
                    previous = await _upload(client, chunks[-1], "video") if plan.extends else None
                    wf = build_workflow(image=uploaded, audios=[audio], masks=[], prompt=prompt,
                                        seed=p["motion"]["seed"] + i, length=plan.length, prev_video=previous)
                    chunk = work / f"{tag}-{p['id']}-{i}.mp4"
                    await _submit(client, wf, chunk, project_id)
                    chunks.append(chunk)
                temporary = work / f"{tag}-{p['id']}-layer.mp4"
                _join_chunks(chunks, Path(p["drive_audio"]), total_frames, temporary)
                # Publish only a complete pass. Cancellation/failure cannot create a cache hit.
                pending = cache / f".{tag}-{p['id']}.mp4"
                shutil.copyfile(temporary, pending)
                pending.replace(target)
            source_reused = reused
            reference_mask = None
            if p.get("reference"):
                target, key, reference_mask, reused = await _transfer_reference(project, p, target, key, client, work, tag)
            matte = cache / f"{p['id']}-{key}-{'reference-v1' if reference_mask else 'u2net-matting-v2'}.mkv"
            matte_reused = matte.is_file() and matte.stat().st_size > 0
            if not matte_reused:
                _status(project_id, stage=f"Extracting {p['name']} from the background (CPU)")
                await asyncio.to_thread(_matte_layer, target, matte)
                if reference_mask:
                    await asyncio.to_thread(_recover_reference_alpha, target, matte, reference_mask)
            layers.append(matte)
            manifest.append({"performer_id": p["id"], "key": key, "file": target.relative_to(cache).as_posix(), "reused": reused,
                             "alpha_file": matte.name, "alpha_reused": matte_reused, "source_reused": source_reused, "reference_transfer": bool(reference_mask)})
    _status(project_id, stage="Compositing performer layers", progress=.95)
    stage = compose_stage(project, work / f"{tag}-stage.png", background_only=True)
    master = compose_layers(project, layers, stage, work / f"{tag}-master.mp4")
    master = _align_visual_timing(project, master, work / f"{tag}-aligned.mp4")
    shutil.copyfile(master, folder / "master-shot.mp4")
    framed = reframe(project, master, work / f"{tag}-framed.mp4")
    final = folder / "performance.mp4"
    _run_ffmpeg(["-i", str(framed), "-i", str(project["master_audio"]), "-map", "0:v", "-map", "1:a",
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", str(final)])
    hd = _upscale(project_id, final, folder / "performance-hd.mp4")
    _status(project_id, stage="Encoding browser preview", progress=.99)
    _browser_preview(hd or final, folder)
    (folder / "layer-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _status(project_id, status="done", stage="Done", progress=1.0, video=str(hd or final),
            video_sd=str(final), master_shot=str(folder / "master-shot.mp4"),
            chunks=len(plans), layers=manifest, upscaled=bool(hd), initial_hold_frames=INITIAL_HOLD_FRAMES, visual_delay_ms=round(float(project.get("visual_delay_ms", 0)) * FPS / 1000) * 1000 / FPS)


def _browser_preview(source: Path, folder: Path) -> Path | None:
    """Portable VP9/Opus preview; retain the full-resolution MP4 export."""
    target = folder / "preview.webm"
    pending = folder / "preview.partial.webm"
    try:
        _run_ffmpeg(["-i", str(source), "-vf", "scale=640:-2", "-c:v", "libvpx-vp9",
                     "-deadline", "realtime", "-cpu-used", "6", "-row-mt", "1", "-threads", "2",
                     "-crf", "32", "-b:v", "0", "-c:a", "libopus", "-b:a", "128k", str(pending)])
        pending.replace(target)
        return target
    except (RuntimeError, OSError):
        pending.unlink(missing_ok=True)
        return None


def _upscale(project_id: str, src: Path, dst: Path) -> Path | None:
    """Real-ESRGAN x{UPSCALE} on the finished video (Universal Enhance worker). Skipped, not faked, if absent."""
    import subprocess

    from . import enhance

    if UPSCALE < 2 or not enhance._available(enhance.OPERATIONS["upscale_ai"])[0]:
        return None
    with httpx.Client(base_url=config.COMFYUI_BASE_URL.rstrip("/"), timeout=5) as client:
        if not _prepare_upscale(client):
            _status(project_id, upscale_skipped_reason="GPU queue busy or sufficient free memory could not be verified")
            return None
    _status(project_id, stage=f"Upscaling x{UPSCALE} (Real-ESRGAN)", progress=0.98)
    proc = subprocess.run([config.MUSIC_STEMS_PYTHON, str(Path(enhance.__file__).with_name("enhance_worker.py")),
                           "upscale_ai", json.dumps({"scale": UPSCALE}), str(src), str(dst)],
                          capture_output=True, text=True, timeout=6 * 3600)
    if proc.returncode != 0 or not dst.is_file():
        return None  # the standard-resolution result is still delivered
    return dst


def _prepare_upscale(client: httpx.Client) -> bool:
    """Release idle generation models before starting the separate enhancement process.

    Do not interrupt queued work, alter memory limits or assume /free is synchronous.
    This is a local preflight, not a cross-application GPU reservation.
    """
    try:
        queue = client.get("/queue")
        queue.raise_for_status()
        if queue.json().get("queue_running") or queue.json().get("queue_pending"):
            return False
        response = client.post("/free", json={"unload_models": True, "free_memory": True})
        response.raise_for_status()
        for _ in range(10):
            response = client.get("/system_stats")
            response.raise_for_status()
            devices = response.json().get("devices", [])
            if devices:
                gpu = devices[0]
                needed = min(6 * 1024**3, gpu.get("vram_total", 0) / 3)
                if needed > 0 and gpu.get("vram_free", 0) >= needed:
                    return True
            time.sleep(.5)
        return False
    except (httpx.HTTPError, ValueError, TypeError):
        return False



async def _submit(client: httpx.AsyncClient, workflow: dict[str, Any], out: Path, project_id: str) -> None:
    resp = await client.post("/prompt", json={"prompt": workflow})
    if resp.status_code >= 400:
        raise RuntimeError(f"ComfyUI rejected the workflow: {resp.text[:400]}")
    prompt_id = resp.json().get("prompt_id")
    if not prompt_id:
        raise RuntimeError("ComfyUI accepted the request without a prompt id.")
    waited = 0.0
    while waited < CHUNK_TIMEOUT:
        if project_id in _cancelled:
            await _stop_prompt(client, prompt_id)
            raise Cancelled()
        entry = (await client.get(f"/history/{prompt_id}")).json().get(prompt_id)
        if entry:
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                detail = next((m[1].get("exception_message") for m in status.get("messages", [])
                               if m and m[0] == "execution_error"), "unknown error")
                raise RuntimeError(f"ComfyUI failed: {str(detail)[:300]}")
            if entry.get("outputs"):
                video = _find_video(entry["outputs"])
                if not video:
                    raise RuntimeError("ComfyUI produced no video.")
                dl = await client.get("/view", params={"filename": video["filename"],
                                                       "subfolder": video.get("subfolder", ""), "type": "output"})
                dl.raise_for_status()
                out.write_bytes(dl.content)
                return
        await asyncio.sleep(POLL)
        waited += POLL
    stopped = await _stop_prompt(client, prompt_id)
    raise TimeoutError("A part took longer than 30 minutes. " +
                       ("Its cancellation was requested." if stopped else
                        "Its cancellation could not be confirmed; check the ComfyUI queue before retrying."))


async def _stop_prompt(client: httpx.AsyncClient, prompt_id: str) -> bool:
    """Cancel only this render's prompt, never an unrelated queued/running job."""
    try:
        response = await client.post(f"/api/jobs/{prompt_id}/cancel")
        if response.status_code != 404:
            response.raise_for_status()
            return bool(response.json().get("cancelled"))
        # Older servers can safely delete a pending id, but their global interrupt
        # cannot guarantee ownership across a queue race. Leave a running job alone.
        response = await client.get("/queue")
        response.raise_for_status()
        queue = response.json()
        if any(len(item) > 1 and item[1] == prompt_id for item in queue.get("queue_pending", [])):
            response = await client.post("/queue", json={"delete": [prompt_id]})
        else:
            return False
        response.raise_for_status()
        return True
    except (httpx.HTTPError, ValueError, TypeError):
        return False


def debug_workflow(project: dict[str, Any]) -> str:
    """The first chunk's workflow, for inspection (names are placeholders)."""
    n = len(project["performers"])
    return json.dumps(build_workflow(image="stage.png", audios=[f"a{i}.wav" for i in range(min(n, 2))],
                                     masks=["mask-0.png", "mask-1.png"][: 2 if n == 2 else 0],
                                     prompt=_prompt_for(project, 0, CHUNK_FRAMES / FPS), seed=1,
                                     length=CHUNK_FRAMES), indent=2)
