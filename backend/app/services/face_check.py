"""Does a picture show a person's face? Asked of a local vision model (Ollama), never a cloud service.

Reference images for a look must not contain a face: the image editor copies the face from a
reference into the avatar. The check answers True, False, or None when the model can't be reached.
"""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from .. import config
from .voice import _free_comfyui_vram

_TIMEOUT_SECONDS = 120.0
_PROMPT = "Does this picture show a human face or a person's head (even a small, blurred or cartoon one)? Reply with only YES or NO."


def image_has_face(path: Path) -> bool | None:
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        _free_comfyui_vram()
        resp = httpx.post(
            f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat", timeout=_TIMEOUT_SECONDS,
            json={"model": config.VISION_MODEL, "stream": False, "think": False, "keep_alive": 0,
                  "options": {"temperature": 0},
                  "messages": [{"role": "user", "content": _PROMPT, "images": [encoded]}]},
        )
        resp.raise_for_status()
        answer = ((resp.json().get("message") or {}).get("content") or "").strip().upper()
    except (httpx.HTTPError, OSError, ValueError):
        return None
    if answer.startswith("YES"):
        return True
    if answer.startswith("NO"):
        return False
    return None
