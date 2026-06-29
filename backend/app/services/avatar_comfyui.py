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
import mimetypes
import uuid
from pathlib import Path
from typing import Any

import httpx

from .. import config
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
        if class_type == "WanInfiniteTalkToVideo":
            inputs["width"] = preset.width
            inputs["height"] = preset.height
            inputs["length"] = preset.frames
        elif class_type == "KSampler":
            inputs["steps"] = preset.steps
            inputs["cfg"] = preset.cfg
    return patched


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


async def generate_talking_avatar(
    image_path: Path,
    audio_path: Path,
    prompt: str,
    out_path: Path,
    preset: AvatarWanPreset | None = None,
) -> None:
    """Run the Wan InfiniteTalk workflow and save the resulting MP4 to out_path."""
    wf_path = _workflow_path()
    workflow = _sanitize(json.loads(wf_path.read_text(encoding="utf-8")), wf_path)
    base = config.COMFYUI_BASE_URL.rstrip("/")
    async with httpx.AsyncClient(base_url=base, timeout=_HTTP_TIMEOUT) as client:
        image_name = await _upload(client, image_path, "image")
        audio_name = await _upload(client, audio_path, "audio")
        patched = _patch(workflow, image_name, audio_name, prompt, preset)
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


def new_output_path() -> Path:
    return config.STORAGE_DIR / "avatar_videos" / f"{uuid.uuid4().hex}.mp4"
