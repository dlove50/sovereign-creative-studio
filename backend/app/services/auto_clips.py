"""Auto clips: find the best short moments in a long video and cut them out.

Local Whisper (CPU) gives a timed transcript, local Qwen picks the moments, and
FFmpeg cuts them. If the model fails or answers badly, a transcript-density
fallback still returns clips, so the feature never dead-ends.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import httpx

from .. import config
from .speech_cleanup import _ffmpeg_bin, probe
from .voice import _free_comfyui_vram

MIN_CLIP_SECONDS = 8.0
MAX_TRANSCRIPT_CHARS = 24000
_TIMEOUT_SECONDS = 900.0

_SYSTEM = (
    "You are a video editor choosing short clips from a long video's transcript. Pick the most "
    "engaging, self-contained moments: a clear idea, a story beat, a strong tip, or a punchline. "
    "Each clip must start at the beginning of a sentence and end at the end of one. Clips must not "
    "overlap. Use the timestamps given. "
    'Reply as JSON only: {"clips": [{"start": seconds, "end": seconds, "title": "short title"}]}'
)


def transcribe_segments(path: Path) -> list[dict]:
    """Timed transcript segments [{start, end, text}] from local Whisper (CPU)."""
    from faster_whisper import WhisperModel  # type: ignore

    config.TRANSCRIPTION_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(
        config.TRANSCRIPTION_MODEL_NAME, device=config.TRANSCRIPTION_DEVICE,
        compute_type=config.TRANSCRIPTION_COMPUTE_TYPE, download_root=str(config.TRANSCRIPTION_MODEL_DIR),
    )
    segments, _ = model.transcribe(str(path), beam_size=1)
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments if s.text.strip()]


def _nearest(value: float, points: list[float]) -> float:
    return min(points, key=lambda p: abs(p - value))


def normalize_clips(raw: list[dict], segments: list[dict], count: int, seconds: float) -> list[dict]:
    """Snap model-suggested clips to sentence boundaries, clamp length, drop overlaps."""
    if not segments:
        return []
    starts = [s["start"] for s in segments]
    ends = [s["end"] for s in segments]
    max_len = max(seconds * 1.5, MIN_CLIP_SECONDS * 2)
    out: list[dict] = []
    for item in raw:
        try:
            start = _nearest(float(item["start"]), starts)
            end = _nearest(float(item["end"]), ends)
        except (KeyError, TypeError, ValueError):
            continue
        if end - start > max_len:  # too long: end at the last sentence that still fits
            fitting = [e for e in ends if start + MIN_CLIP_SECONDS <= e <= start + max_len]
            if not fitting:
                continue
            end = fitting[-1]
        if end - start < MIN_CLIP_SECONDS:
            continue
        if any(start < c["end"] and end > c["start"] for c in out):
            continue
        out.append({"start": start, "end": end, "title": str(item.get("title") or "").strip()[:80]})
        if len(out) == count:
            break
    return sorted(out, key=lambda c: c["start"])


def fallback_clips(segments: list[dict], count: int, seconds: float) -> list[dict]:
    """Densest-speech windows of about `seconds`, snapped to sentences, non-overlapping."""
    windows = []
    for i, first in enumerate(segments):
        end_i, words = i, 0
        while end_i < len(segments) and segments[end_i]["end"] - first["start"] <= seconds:
            words += len(segments[end_i]["text"].split())
            end_i += 1
        if end_i > i and segments[end_i - 1]["end"] - first["start"] >= MIN_CLIP_SECONDS:
            windows.append((words, first["start"], segments[end_i - 1]["end"], first["text"]))
    chosen: list[dict] = []
    for _, start, end, text in sorted(windows, reverse=True):
        if all(not (start < c["end"] and end > c["start"]) for c in chosen):
            chosen.append({"start": start, "end": end, "title": " ".join(text.split()[:6])})
        if len(chosen) == count:
            break
    return sorted(chosen, key=lambda c: c["start"])


def pick_clips_with_qwen(segments: list[dict], count: int, seconds: float, model: str | None = None) -> list[dict]:
    """Ask local Qwen for clips; returns the raw suggestions (may be empty)."""
    transcript = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments)[:MAX_TRANSCRIPT_CHARS]
    user = f"Pick the best {count} clips, each about {int(seconds)} seconds long.\n\nTranscript:\n{transcript}"
    _free_comfyui_vram()
    resp = httpx.post(
        f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/chat", timeout=_TIMEOUT_SECONDS,
        json={"model": model or config.VIDEO_AGENT_MODEL, "stream": False, "think": False, "format": "json",
              "keep_alive": 0, "options": {"temperature": 0.3},
              "messages": [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]},
    )
    resp.raise_for_status()
    content = (resp.json().get("message") or {}).get("content") or "{}"
    clips = json.loads(content).get("clips")
    return clips if isinstance(clips, list) else []


def cut(src: Path, out: Path, start: float, end: float, has_video: bool) -> None:
    args = [_ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src)]
    args += ["-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac"] if has_video else ["-c:a", "aac"]
    result = subprocess.run([*args, str(out)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg could not cut a clip: {result.stderr.strip()[-300:]}")


def make_clips(src: Path, out_dir: Path, stem: str, count: int, seconds: int) -> dict:
    duration, has_video = probe(src)
    segments = transcribe_segments(src)
    if not segments:
        raise RuntimeError("No speech was found in this file, so there is nothing to clip.")
    method = "ai"
    try:
        clips = normalize_clips(pick_clips_with_qwen(segments, count, seconds), segments, count, seconds)
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        clips = []
    if not clips:
        method = "fallback"
        clips = fallback_clips(segments, count, seconds)
    if not clips:
        raise RuntimeError("The speech is too short to make clips. Try a longer video.")
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".mp4" if has_video else ".m4a"
    results = []
    for i, clip in enumerate(clips, start=1):
        target = out_dir / f"{stem}_clip{i}{suffix}"
        cut(src, target, clip["start"], clip["end"], has_video)
        results.append({**clip, "seconds": round(clip["end"] - clip["start"], 1), "file": target.name})
    return {"duration": round(duration, 1), "method": method, "clips": results, "has_video": has_video}
