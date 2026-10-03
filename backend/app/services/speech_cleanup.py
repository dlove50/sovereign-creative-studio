"""Speech cleanup: cut long pauses and filler words ("um", "uh") from a video or audio file.

Pauses come from FFmpeg's silence detector; filler words come from local Whisper
word timestamps (CPU). Both are turned into "remove" ranges, merged, and the rest
is re-joined with FFmpeg. Nothing leaves the computer and no credits are charged.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from .. import config
from .audio_merge import _ffmpeg

FILLER_WORDS = {"um", "uh", "uhm", "umm", "er", "erm", "ah", "hmm", "mm", "mmm"}
MIN_PAUSE_SECONDS = 0.6   # silences shorter than this are natural and kept
PAUSE_KEEP_SECONDS = 0.15  # keep this much of each trimmed pause on both sides
SILENCE_DB = -35
MIN_KEEP_SECONDS = 0.05


def plan_keep(duration: float, removals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping removal ranges and return the (start, end) ranges to keep."""
    merged: list[list[float]] = []
    for start, end in sorted((max(0.0, s), min(duration, e)) for s, e in removals if e > s):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in merged:
        if start - cursor >= MIN_KEEP_SECONDS:
            keep.append((cursor, start))
        cursor = end
    if duration - cursor >= MIN_KEEP_SECONDS:
        keep.append((cursor, duration))
    return keep


def _ffmpeg_bin() -> str:
    path = _ffmpeg()
    if not path:
        raise RuntimeError("FFmpeg is required for speech cleanup.")
    return path


def probe(path: Path) -> tuple[float, bool]:
    """(duration in seconds, has_video) from ffmpeg's banner."""
    out = subprocess.run([_ffmpeg_bin(), "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
    if not m:
        raise RuntimeError("Could not read this file. Try an MP4, MOV, MP3 or WAV.")
    duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return duration, bool(re.search(r"Stream #\d+:\d+.*Video:", out))


def detect_pauses(path: Path, duration: float) -> list[tuple[float, float]]:
    """Silent stretches long enough to trim, as ranges that keep a small pad each side."""
    out = subprocess.run(
        [_ffmpeg_bin(), "-hide_banner", "-i", str(path), "-vn", "-af",
         f"silencedetect=noise={SILENCE_DB}dB:d={MIN_PAUSE_SECONDS}", "-f", "null", "-"],
        capture_output=True, text=True,
    ).stderr
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?\d+(?:\.\d+)?)", out)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*(-?\d+(?:\.\d+)?)", out)]
    if len(starts) > len(ends):  # file ends in silence
        ends.append(duration)
    ranges = []
    for start, end in zip(starts, ends):
        start, end = max(0.0, start), min(duration, end)
        if end - start > 2 * PAUSE_KEEP_SECONDS:
            ranges.append((start + PAUSE_KEEP_SECONDS, end - PAUSE_KEEP_SECONDS))
    return ranges


def detect_fillers(path: Path) -> list[tuple[float, float]]:
    """Time ranges of filler words, from local Whisper word timestamps (CPU)."""
    from faster_whisper import WhisperModel  # type: ignore

    config.TRANSCRIPTION_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(
        config.TRANSCRIPTION_MODEL_NAME, device=config.TRANSCRIPTION_DEVICE,
        compute_type=config.TRANSCRIPTION_COMPUTE_TYPE, download_root=str(config.TRANSCRIPTION_MODEL_DIR),
    )
    segments, _ = model.transcribe(str(path), word_timestamps=True, beam_size=1)
    ranges = []
    for segment in segments:
        for word in segment.words or []:
            if re.sub(r"[^a-z]", "", word.word.lower()) in FILLER_WORDS:
                ranges.append((word.start, word.end))
    return ranges


def _cut(src: Path, out: Path, keep: list[tuple[float, float]], has_video: bool) -> None:
    """Re-join the kept ranges. The filter graph goes in a file (long scripts overflow the command line)."""
    lines, labels = [], ""
    for i, (start, end) in enumerate(keep):
        if has_video:
            lines.append(f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{i}]")
        lines.append(f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{i}]")
        labels += f"[v{i}]" if has_video else ""
        labels += f"[a{i}]"
    v, a = (1, 1) if has_video else (0, 1)
    lines.append(f"{labels}concat=n={len(keep)}:v={v}:a={a}" + ("[v][a]" if has_video else "[a]"))
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as script:
        script.write(";\n".join(lines))
    try:
        args = [_ffmpeg_bin(), "-y", "-v", "error", "-i", str(src), "-filter_complex_script", script.name]
        args += ["-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac"] if has_video \
            else ["-map", "[a]", "-c:a", "aac"]
        result = subprocess.run([*args, str(out)], capture_output=True, text=True)
    finally:
        Path(script.name).unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg could not cut the file: {result.stderr.strip()[-300:]}")


def clean(src: Path, out: Path, *, remove_pauses: bool = True, remove_fillers: bool = True) -> dict:
    """Cut pauses and/or fillers from `src` into `out`. Returns what changed."""
    duration, has_video = probe(src)
    pauses = detect_pauses(src, duration) if remove_pauses else []
    fillers = detect_fillers(src) if remove_fillers else []
    keep = plan_keep(duration, pauses + fillers)
    if not keep:
        raise RuntimeError("Nothing would be left after cleanup. Try keeping pauses or fillers.")
    if not (pauses or fillers):
        out.write_bytes(src.read_bytes())
        new_duration = duration
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        _cut(src, out, keep, has_video)
        new_duration = float(sum(end - start for start, end in keep))
    return {
        "original_seconds": round(duration, 2), "new_seconds": round(new_duration, 2),
        "seconds_removed": round(duration - new_duration, 2),
        "pauses_removed": len(pauses), "fillers_removed": len(fillers), "has_video": has_video,
    }
