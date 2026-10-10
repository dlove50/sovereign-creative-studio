"""Clone a real person from a video of them talking.

This does NOT train a model on the footage. It takes the sharpest well-framed still as the
avatar's photo and the speech as a VibeVoice voice sample, so the avatar looks like the person
and sounds like them. Movement comes from the talking-avatar model, not from the footage.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import httpx

from .. import config
from .speech_cleanup import _ffmpeg_bin, probe

MIN_SECONDS = 8.0
MAX_VOICE_SECONDS = 60
_FRAME_POINTS = (0.15, 0.3, 0.45, 0.6, 0.75)
_NAME_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


def voice_name_for(person: str) -> str:
    """Name VibeVoice accepts (letters, digits, dash)."""
    return _NAME_SAFE.sub("-", person).strip("-")[:40] or "voice"


def _frame_sharpness(path: Path) -> float:
    """Higher means sharper: mean of an edge filter via ffmpeg signalstats (YAVG of the edges)."""
    out = subprocess.run(
        [_ffmpeg_bin(), "-hide_banner", "-i", str(path), "-vf", "edgedetect,signalstats,metadata=print", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    values = [float(v) for v in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", out)]
    return values[0] if values else 0.0


def best_frame(video: Path, out: Path, duration: float) -> None:
    """Save the sharpest of a few evenly spread frames as a JPEG."""
    candidates = []
    for i, point in enumerate(_FRAME_POINTS):
        frame = out.with_name(f"{out.stem}_cand{i}.jpg")
        subprocess.run(
            [_ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{duration * point:.2f}", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(frame)],
            capture_output=True,
        )
        if frame.is_file():
            candidates.append((_frame_sharpness(frame), frame))
    if not candidates:
        raise RuntimeError("Could not read any picture from that video.")
    best = max(candidates, key=lambda c: c[0])[1]
    best.replace(out)
    for _, frame in candidates:
        frame.unlink(missing_ok=True)


def extract_voice_sample(video: Path, out: Path) -> None:
    """Mono 24 kHz speech, loudness-normalised, capped at MAX_VOICE_SECONDS."""
    result = subprocess.run(
        [_ffmpeg_bin(), "-y", "-v", "error", "-i", str(video), "-t", str(MAX_VOICE_SECONDS), "-vn", "-ac", "1", "-ar", "24000",
         "-af", "highpass=f=70,loudnorm=I=-20:TP=-2", str(out)],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not out.is_file():
        raise RuntimeError("That video has no usable sound, so the voice could not be cloned.")


def register_voice(name: str, sample: Path) -> str | None:
    """Add the sample to the local VibeVoice app. Returns the clone's name, or None with no error
    raised when the app is not running (the caller reports that the voice was skipped)."""
    try:
        with sample.open("rb") as handle:
            resp = httpx.post(f"{config.VIBEVOICE_BASE_URL}/api/voices", params={"name": name}, files={"file": (sample.name, handle)}, timeout=60.0)
    except httpx.HTTPError:
        from . import voice_studio

        if not voice_studio.installed():
            return None
        try:
            return voice_studio.add_voice_file(name, sample)
        except voice_studio.VoiceStudioError as exc:
            raise RuntimeError(str(exc)) from exc
    if resp.status_code == 409:
        raise RuntimeError(f"A cloned voice named {name} already exists. Pick a different name.")
    if resp.status_code >= 400:
        raise RuntimeError(f"The voice app refused the sample: {resp.text[:160]}")
    return resp.json().get("name")


def clone(video: Path, workdir: Path, person: str) -> dict:
    duration, has_video = probe(video)
    if not has_video:
        raise RuntimeError("Upload a video that shows your face.")
    if duration < MIN_SECONDS:
        raise RuntimeError(f"The video is {duration:.0f} s. Use at least {MIN_SECONDS:.0f} s of you talking.")
    workdir.mkdir(parents=True, exist_ok=True)
    frame = workdir / "face.jpg"
    sample = workdir / "voice.wav"
    best_frame(video, frame, duration)
    extract_voice_sample(video, sample)
    return {"frame": frame, "sample": sample, "voice_name": register_voice(voice_name_for(person), sample), "duration": duration}
