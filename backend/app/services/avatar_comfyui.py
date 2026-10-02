"""Real ComfyUI talking-avatar adapter (Phase 16C, Wan InfiniteTalk).

Loads the avatar workflow scaffold, patches the avatar image + voice audio + model
names, submits to ComfyUI, polls /history, downloads the MP4 and saves it locally.
Mirrors the proven image-to-video adapter. This only runs when avatar_readiness()
is fully ready (node + workflow + weights present); otherwise the job is
setup_required and this is never called.
"""
from __future__ import annotations

import asyncio
import json
import math
import mimetypes
import shutil
import subprocess
import tempfile
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .. import config
from .audio_merge import _ffmpeg
from .avatar_presets import AvatarWanPreset, resolve_preset

_IMAGE_PH = "__SOURCE_IMAGE__"
_AUDIO_PH = "__SOURCE_AUDIO__"
_PROMPT_PH = "__PROMPT__"
_VIDEO_MODEL_PH = "__VIDEO_MODEL__"
_PATCH_PH = "__INFINITETALK_PATCH__"
_AUDIO_ENCODER_PH = "__AUDIO_ENCODER__"

_POLL_INTERVAL = 2.0
_POLL_MAX_ATTEMPTS = 300  # ~10 minutes
_HTTP_TIMEOUT = 60.0
_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv"}

FPS = 25
MOTION_FRAMES = 9  # frames of the previous chunk InfiniteTalk continues from
_TALK_NODE = "WanInfiniteTalkToVideo"
_PREV_LOADER_ID = "90"
_PREV_FRAMES_ID = "91"
_LORA_ID = "92"


@dataclass(frozen=True)
class ChunkPlan:
    """One InfiniteTalk render. Audio is sliced from audio_start_frame for
    audio_frames frames; extend chunks also receive the previous chunk's video."""
    audio_start_frame: int
    audio_frames: int
    length: int
    extends: bool


def _round_up_4n1(frames: int) -> int:
    """Wan latents need length = 4n + 1."""
    return 4 * math.ceil(max(frames - 1, 0) / 4) + 1


def plan_chunks(audio_seconds: float, chunk_frames: int, motion: int = MOTION_FRAMES) -> tuple[list[ChunkPlan], int]:
    """Split speech into overlapping InfiniteTalk renders.

    Returns the chunk plans and the total frame count of the final video. An
    extend chunk continues from the last `motion` frames of the previous chunk;
    the node reads its audio window starting (prev_length - motion) frames into
    the audio it is given, so that audio starts where the previous chunk started.
    """
    total = max(motion, math.ceil(audio_seconds * FPS))
    if total <= chunk_frames:
        length = _round_up_4n1(total)
        return [ChunkPlan(0, length, length, False)], total
    plans = [ChunkPlan(0, chunk_frames, chunk_frames, False)]
    prev_start, covered = 0, chunk_frames
    while covered < total:
        plans.append(ChunkPlan(prev_start, 2 * chunk_frames - motion, chunk_frames, True))
        prev_start += chunk_frames - motion
        covered += chunk_frames - motion
    return plans, total


def _workflow_path() -> Path:
    path = Path(config.AVATAR_WAN_WORKFLOW_PATH)
    return path if path.is_absolute() else config.BASE_DIR / path


def _sanitize(workflow: dict, path: Path) -> dict:
    """Reject UI-export workflows; strip non-API helper nodes (e.g. _setup_note)."""
    if not isinstance(workflow, dict):
        raise RuntimeError(f"Avatar workflow {path} must be a ComfyUI API JSON object.")
    if "nodes" in workflow or "links" in workflow:
        raise RuntimeError(f"Avatar workflow {path} is a ComfyUI UI export. Save it as API Format.")
    sanitized: dict[str, dict] = {}
    for node_id, node in workflow.items():
        if isinstance(node, dict) and "class_type" in node:
            sanitized[str(node_id)] = node
    if not sanitized:
        raise RuntimeError(f"Avatar workflow {path} has no executable API nodes.")
    return sanitized


def _patch(
    workflow: dict,
    image_name: str,
    audio_name: str,
    prompt: str,
    preset: AvatarWanPreset | None = None,
    *,
    length: int | None = None,
    prev_video_name: str | None = None,
) -> dict:
    preset = preset or resolve_preset()
    replacements = {
        _IMAGE_PH: image_name,
        _AUDIO_PH: audio_name,
        _PROMPT_PH: prompt,
        _VIDEO_MODEL_PH: config.AVATAR_WAN_MODEL_NAME,
        _PATCH_PH: config.AVATAR_INFINITETALK_PATCH_NAME,
        _AUDIO_ENCODER_PH: config.AVATAR_AUDIO_ENCODER_NAME,
    }

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, str):
            for ph, rep in replacements.items():
                if value == ph:
                    return rep
                if ph in value:
                    value = value.replace(ph, str(rep))
            return value
        return value

    patched = walk(workflow)
    for node in patched.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = node.get("class_type")
        if class_type == _TALK_NODE:
            inputs["width"] = preset.width
            inputs["height"] = preset.height
            inputs["length"] = length or preset.frames
            if prev_video_name:
                inputs["previous_frames"] = [_PREV_FRAMES_ID, 0]
        elif class_type == "KSampler":
            inputs["steps"] = preset.steps
            inputs["cfg"] = preset.cfg
    if prev_video_name:
        patched[_PREV_LOADER_ID] = {"class_type": "LoadVideo", "inputs": {"file": prev_video_name}}
        patched[_PREV_FRAMES_ID] = {"class_type": "GetVideoComponents", "inputs": {"video": [_PREV_LOADER_ID, 0]}}
    if config.AVATAR_WAN_LORA_NAME:
        _insert_lora(patched)
    return patched


def _insert_lora(workflow: dict) -> None:
    """Route the talking node's model through the step-distill LoRA."""
    talk = next(n for n in workflow.values() if n.get("class_type") == _TALK_NODE)
    workflow[_LORA_ID] = {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {
            "model": talk["inputs"]["model"],
            "lora_name": config.AVATAR_WAN_LORA_NAME,
            "strength_model": config.AVATAR_WAN_LORA_STRENGTH,
        },
    }
    talk["inputs"]["model"] = [_LORA_ID, 0]


async def _upload(client: httpx.AsyncClient, local: Path, kind: str) -> str:
    field = "image"  # ComfyUI's /upload/image also accepts audio into the input dir
    content_type = mimetypes.guess_type(local.name)[0] or ("audio/wav" if kind == "audio" else "image/png")
    files = {field: (local.name, local.read_bytes(), content_type)}
    resp = await client.post("/upload/image", files=files, data={"overwrite": "true"})
    resp.raise_for_status()
    body = resp.json()
    name = body.get("name")
    if not name:
        raise RuntimeError("ComfyUI did not return an uploaded file name")
    sub = body.get("subfolder")
    return f"{sub}/{name}" if sub else name


async def _await_outputs(client: httpx.AsyncClient, prompt_id: str) -> dict:
    for _ in range(_POLL_MAX_ATTEMPTS):
        resp = await client.get(f"/history/{prompt_id}")
        resp.raise_for_status()
        entry = resp.json().get(prompt_id)
        if entry:
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise RuntimeError("ComfyUI talking-avatar workflow failed during execution")
            if entry.get("outputs"):
                return entry["outputs"]
        await asyncio.sleep(_POLL_INTERVAL)
    raise TimeoutError("ComfyUI talking-avatar generation timed out")


def _find_video(outputs: dict) -> dict | None:
    for node_output in outputs.values():
        for key in ("videos", "gifs", "files", "images"):
            for item in node_output.get(key, []) or []:
                if Path(str(item.get("filename", ""))).suffix.lower() in _VIDEO_EXTS:
                    return item
    return None


async def _render(client: httpx.AsyncClient, patched: dict, out_path: Path) -> None:
    resp = await client.post("/prompt", json={"prompt": patched})
    resp.raise_for_status()
    prompt_id = resp.json().get("prompt_id")
    if not prompt_id:
        raise RuntimeError("ComfyUI did not return a prompt_id")
    outputs = await _await_outputs(client, prompt_id)
    video = _find_video(outputs)
    if not video:
        raise RuntimeError("ComfyUI produced no video output")
    dl = await client.get(
        "/view",
        params={"filename": video["filename"], "subfolder": video.get("subfolder", ""), "type": video.get("type", "output")},
    )
    dl.raise_for_status()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(dl.content)
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RuntimeError("Saved avatar video is empty")


def _audio_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())
    except (wave.Error, EOFError) as exc:
        raise RuntimeError(f"Voice audio must be a WAV file: {exc}") from exc


def _run_ffmpeg(args: list[str]) -> None:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to join long talking-avatar videos.")
    result = subprocess.run([ffmpeg, "-y", "-v", "error", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr.strip()[-400:]}")


def _slice_audio(src: Path, plan: ChunkPlan, dst: Path) -> None:
    """Cut the chunk's audio window, padding with silence past the end of speech."""
    _run_ffmpeg([
        "-ss", f"{plan.audio_start_frame / FPS:.3f}", "-i", str(src),
        "-af", "apad", "-t", f"{plan.audio_frames / FPS:.3f}", str(dst),
    ])


def _join_chunks(chunks: list[Path], audio: Path, total_frames: int, out_path: Path) -> None:
    """Drop each extend chunk's repeated motion frames, concatenate, add the full voice."""
    inputs: list[str] = []
    parts: list[str] = []
    for i, chunk in enumerate(chunks):
        inputs += ["-i", str(chunk)]
        start = 0 if i == 0 else MOTION_FRAMES
        parts.append(f"[{i}:v]trim=start_frame={start},setpts=PTS-STARTPTS[v{i}]")
    joined = "".join(f"[v{i}]" for i in range(len(chunks)))
    graph = ";".join(parts) + f";{joined}concat=n={len(chunks)}:v=1:a=0,trim=end_frame={total_frames}[v]"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg([
        *inputs, "-i", str(audio), "-filter_complex", graph,
        "-map", "[v]", "-map", f"{len(chunks)}:a", "-c:v", "libx264", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out_path),
    ])


async def generate_talking_avatar(
    image_path: Path,
    audio_path: Path,
    prompt: str,
    out_path: Path,
    preset: AvatarWanPreset | None = None,
) -> None:
    """Render the whole voice clip as a talking avatar and save the MP4 to out_path.

    Speech longer than one preset chunk is rendered as overlapping InfiniteTalk
    extensions (each continuing from the previous chunk's last frames) and joined.
    """
    preset = preset or resolve_preset()
    wf_path = _workflow_path()
    workflow = _sanitize(json.loads(wf_path.read_text(encoding="utf-8")), wf_path)
    plans, total_frames = plan_chunks(_audio_seconds(audio_path), preset.frames)
    base = config.COMFYUI_BASE_URL.rstrip("/")
    async with httpx.AsyncClient(base_url=base, timeout=_HTTP_TIMEOUT) as client:
        image_name = await _upload(client, image_path, "image")
        if len(plans) == 1:
            audio_name = await _upload(client, audio_path, "audio")
            patched = _patch(workflow, image_name, audio_name, prompt, preset, length=plans[0].length)
            await _render(client, patched, out_path)
            return

        tag = uuid.uuid4().hex[:12]
        work = Path(tempfile.mkdtemp(prefix="avatar_chunks_"))
        try:
            chunks: list[Path] = []
            for i, plan in enumerate(plans):
                chunk_audio = work / f"{tag}_a{i}.wav"
                _slice_audio(audio_path, plan, chunk_audio)
                audio_name = await _upload(client, chunk_audio, "audio")
                prev_name = await _upload(client, chunks[-1], "video") if plan.extends else None
                patched = _patch(
                    workflow, image_name, audio_name, prompt, preset,
                    length=plan.length, prev_video_name=prev_name,
                )
                chunk_video = work / f"{tag}_v{i}.mp4"
                await _render(client, patched, chunk_video)
                chunks.append(chunk_video)
            _join_chunks(chunks, audio_path, total_frames, out_path)
        finally:
            shutil.rmtree(work, ignore_errors=True)
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RuntimeError("Saved avatar video is empty")


def new_output_path() -> Path:
    return config.STORAGE_DIR / "avatar_videos" / f"{uuid.uuid4().hex}.mp4"
