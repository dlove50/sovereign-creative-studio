"""Video agent: turn a plain-language request into a spoken script with local Qwen.

The script is then voiced and animated by the existing voice + talking-avatar
pipeline. Ollama shares the 16 GB GPU with ComfyUI, so ComfyUI is asked to free
VRAM first and Ollama unloads the model right after (keep_alive 0).
"""
from __future__ import annotations

import json
import re

import httpx

from .. import config
from .voice import _free_comfyui_vram

WORDS_PER_SECOND = 2.5  # a calm presenter pace
_TIMEOUT_SECONDS = 600.0

_SYSTEM = (
    "You write scripts for a talking-head video. One presenter speaks directly to the camera "
    "in first person. Write only the words they say out loud: no stage directions, no "
    "brackets, no emojis, no hashtags, no headings, no lists with symbols. Use short, natural "
    "sentences that are easy to say. "
    'Reply as JSON with exactly two keys: {"title": "a short title", "script": "the spoken words"}.'
)


def target_words(seconds: int) -> int:
    return max(10, round(seconds * WORDS_PER_SECOND))


def clean_script(text: str) -> str:
    """Strip things a presenter can't say: stage directions, markup, emoji."""
    text = re.sub(r"\[[^\]]*\]|\([^)]*(pause|beat|smile|laugh|music)[^)]*\)", " ", text, flags=re.I)
    text = re.sub(r"[*_#>`~]", "", text)
    text = re.sub(r"[\U0001F300-\U0001FAFF☀-➿]", "", text)
    return " ".join(text.split())


def write_script(prompt: str, seconds: int, model: str | None = None) -> dict:
    """Ask Ollama for a {title, script} for `prompt`, about `seconds` long. Raises on failure."""
    model = model or config.VIDEO_AGENT_MODEL
    words = target_words(seconds)
    user = f"{prompt.strip()}\n\nMake it about {seconds} seconds long when spoken: about {words} words."
    _free_comfyui_vram()
    try:
        resp = httpx.post(
            f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat",
            timeout=_TIMEOUT_SECONDS,
            json={
                "model": model,
                "stream": False,
                "think": False,
                "format": "json",
                "keep_alive": 0,
                "options": {"temperature": 0.7},
                "messages": [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            },
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Ollama is not reachable at {config.OLLAMA_BASE_URL}. Start Ollama and try again.") from exc
    if resp.status_code == 404:
        raise RuntimeError(f"The script model '{model}' isn't installed. Run: ollama pull {model}")
    if resp.status_code >= 400:
        raise RuntimeError(f"Ollama failed ({resp.status_code}): {resp.text[:200]}")
    content = ((resp.json().get("message") or {}).get("content") or "").strip()
    try:
        data = json.loads(content)
        title, script = str(data.get("title") or "").strip(), clean_script(str(data.get("script") or ""))
    except (json.JSONDecodeError, AttributeError):
        title, script = "", clean_script(content)
    if not script:
        raise RuntimeError("The model returned an empty script. Try rewording your request.")
    return {"title": title or prompt.strip()[:60], "script": script, "model": model, "target_words": words}
