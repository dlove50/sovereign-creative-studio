"""Translate videos: local Whisper transcript, local Qwen translation, subtitles out.

Languages are whatever Qwen translates well; spoken output is limited by the installed voices
(Piper has English, Spanish and French here; the page picks the matching voice), so the page offers
subtitles plus a script for the avatar tools.
"""
from __future__ import annotations

import json

import httpx

from .. import config
from .auto_clips import transcribe_segments
from .voice import _free_comfyui_vram

LANGUAGES = [
    "Spanish", "French", "German", "Italian", "Portuguese", "Dutch", "Polish", "Turkish", "Russian",
    "Ukrainian", "Arabic", "Hindi", "Bengali", "Indonesian", "Vietnamese", "Thai", "Japanese",
    "Korean", "Chinese (Simplified)", "Chinese (Traditional)", "English",
]
BATCH_SIZE = 20
SCENE_CHARS = 1200
_TIMEOUT_SECONDS = 900.0
_SYSTEM = (
    "You are a professional subtitle translator. Translate each numbered line into {language}. "
    "Keep the meaning, tone and names; keep each line short enough to read as a subtitle; never merge "
    "or split lines. "
    'Reply as JSON only: {{"lines": ["translation of line 1", "translation of line 2", ...]}} with exactly '
    "as many entries as input lines."
)


def translate_lines(lines: list[str], language: str, model: str | None = None) -> list[str]:
    """Translate `lines` in order. Raises RuntimeError on any failure (never returns partial text)."""
    if language not in LANGUAGES:
        raise RuntimeError(f"Choose one of the listed languages (got '{language}').")
    out: list[str] = []
    _free_comfyui_vram()
    for start in range(0, len(lines), BATCH_SIZE):
        batch = lines[start:start + BATCH_SIZE]
        numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(batch, start=1))
        try:
            resp = httpx.post(
                f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat", timeout=_TIMEOUT_SECONDS,
                json={"model": model or config.VIDEO_AGENT_MODEL, "stream": False, "think": False,
                      "format": "json", "keep_alive": 0, "options": {"temperature": 0.2},
                      "messages": [{"role": "system", "content": _SYSTEM.format(language=language)},
                                   {"role": "user", "content": numbered}]},
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Ollama is not reachable at {config.OLLAMA_BASE_URL}. Start Ollama and try again.") from exc
        if resp.status_code >= 400:
            raise RuntimeError(f"The translation model failed ({resp.status_code}). Is '{config.VIDEO_AGENT_MODEL}' installed?")
        try:
            lines_out = json.loads((resp.json().get("message") or {}).get("content") or "{}").get("lines")
        except json.JSONDecodeError:
            lines_out = None
        if not isinstance(lines_out, list) or len(lines_out) != len(batch):
            raise RuntimeError("The translation came back malformed. Try again.")
        out.extend(str(t).strip() for t in lines_out)
    return out


def _stamp(seconds: float, sep: str) -> str:
    ms = int(round(max(seconds, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(segments: list[dict]) -> str:
    return "".join(
        f"{i}\n{_stamp(s['start'], ',')} --> {_stamp(s['end'], ',')}\n{s['text']}\n\n"
        for i, s in enumerate(segments, start=1)
    )


def to_vtt(segments: list[dict]) -> str:
    return "WEBVTT\n\n" + "".join(
        f"{_stamp(s['start'], '.')} --> {_stamp(s['end'], '.')}\n{s['text']}\n\n" for s in segments
    )


def split_scenes(texts: list[str], limit: int = SCENE_CHARS) -> list[str]:
    """Group translated lines into scene scripts of at most `limit` characters, never splitting a line."""
    scenes: list[str] = []
    current = ""
    for text in texts:
        text = " ".join(text.split())
        if not text:
            continue
        if current and len(current) + 1 + len(text) > limit:
            scenes.append(current)
            current = ""
        current = f"{current} {text}".strip() if current else text[:limit]
    if current:
        scenes.append(current)
    return scenes


def translate_media(path, language: str, model: str | None = None) -> dict:
    segments = transcribe_segments(path)
    if not segments:
        raise RuntimeError("No speech was found in that file.")
    translated = translate_lines([s["text"] for s in segments], language, model)
    result = [{**s, "original": s["text"], "text": t} for s, t in zip(segments, translated)]
    return {"language": language, "segments": result, "srt": to_srt(result), "vtt": to_vtt(result)}
