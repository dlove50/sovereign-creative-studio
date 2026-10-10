"""Burn captions into a finished video: local Whisper for the words and timing, FFmpeg for the pixels."""
from __future__ import annotations

import subprocess
import tempfile
import textwrap
from pathlib import Path

from .auto_clips import transcribe_segments
from .speech_cleanup import _ffmpeg_bin, probe
from .translate import to_srt

MAX_LINE_CHARS = 28
MAX_LINES = 2
# FontSize is in libass script units (the video is scaled to 288 high), so 10 is about 3.5% of the picture height.
STYLE = "FontName=Arial,FontSize=10,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=18"


def wrap_caption(text: str) -> str:
    """At most MAX_LINES lines of MAX_LINE_CHARS; longer text is cut at a word."""
    lines = textwrap.wrap(" ".join(text.split()), width=MAX_LINE_CHARS)
    return "\n".join(lines[:MAX_LINES])


def split_for_captions(segments: list[dict]) -> list[dict]:
    """Break long Whisper segments into caption-sized pieces with proportional timing."""
    out: list[dict] = []
    capacity = MAX_LINE_CHARS * MAX_LINES
    for seg in segments:
        text = " ".join(seg["text"].split())
        if not text:
            continue
        chunks = textwrap.wrap(text, width=capacity)
        total = sum(len(c) for c in chunks) or 1
        cursor = seg["start"]
        for chunk in chunks:
            length = (seg["end"] - seg["start"]) * len(chunk) / total
            out.append({"start": cursor, "end": cursor + length, "text": wrap_caption(chunk)})
            cursor += length
    return out


def add_captions(video: Path, out: Path) -> dict:
    """Write `out` (the video with captions burned in) and return {"srt": text, "captions": count}."""
    _, has_video = probe(video)
    if not has_video:
        raise RuntimeError("Captions need a video, not an audio file.")
    segments = transcribe_segments(video)
    captions = split_for_captions(segments)
    if not captions:
        raise RuntimeError("No speech was found, so there is nothing to caption.")
    srt = to_srt(captions)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "captions.srt").write_text(srt, encoding="utf-8")
        # Run inside the temp folder with a relative name: Windows drive-letter paths break the filter syntax.
        result = subprocess.run(
            [_ffmpeg_bin(), "-y", "-v", "error", "-i", str(video.resolve()), "-vf", f"subtitles=captions.srt:force_style='{STYLE}'",
             "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", str(out.resolve())],
            capture_output=True, text=True, cwd=tmp,
        )
    if result.returncode != 0 or not out.is_file():
        raise RuntimeError(f"Captions could not be added: {result.stderr.strip()[-300:]}")
    return {"srt": srt, "captions": len(captions)}
