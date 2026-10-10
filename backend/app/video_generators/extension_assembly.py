"""Append a generated continuation while retaining source picture and sound."""
import json
import math
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path


def _probe(path: Path) -> tuple[dict, float, bool]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    metadata = json.loads(result.stdout)
    video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    duration_value = video.get("duration")
    if duration_value in (None, "N/A", ""):
        duration_value = metadata.get("format", {}).get("duration")
    duration = float(duration_value)
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("Cannot extend a video with an invalid duration")
    return video, duration, any(s["codec_type"] == "audio" for s in metadata["streams"])


def append_continuation(source: Path, continuation: Path, destination: Path) -> float:
    """Normalize and append; never modify either input, even on failure.

    Source audio is retained through its full video duration. Silent segments get
    silence instead of borrowing/repeating source speech. Any continuation audio
    is retained as well. Encoding changes are necessary for mismatched formats.
    """
    if destination.resolve() in (source.resolve(), continuation.resolve()):
        raise ValueError("Extension destination must differ from both inputs")
    original, source_duration, source_audio = _probe(source)
    _, continuation_duration, continuation_audio = _probe(continuation)
    fps = Fraction(original.get("avg_frame_rate", "0/1"))
    if fps <= 0:
        raise RuntimeError("Source video has no valid frame rate")
    width = (int(original["width"]) + 1) // 2 * 2
    height = (int(original["height"]) + 1) // 2 * 2
    filters = []
    for index, duration, has_audio in (
        (0, source_duration, source_audio), (1, continuation_duration, continuation_audio)
    ):
        filters.append(
            f"[{index}:v:0]setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"fps={fps},format=yuv420p[v{index}]"
        )
        audio = f"[{index}:a:0]" if has_audio else "anullsrc=r=48000:cl=stereo,"
        filters.append(
            f"{audio}aresample=48000,aformat=channel_layouts=stereo,"
            f"apad,atrim=duration={duration},asetpts=PTS-STARTPTS[a{index}]"
        )
    filters.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="extension-", dir=destination.parent) as temporary:
        result = Path(temporary) / "assembled.mp4"
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
             "-i", str(source), "-i", str(continuation), "-filter_complex", ";".join(filters),
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast",
             "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(result)],
            capture_output=True, text=True, check=True, timeout=1800,
        )
        _, actual_duration, has_audio = _probe(result)
        expected = source_duration + continuation_duration
        if not has_audio or abs(actual_duration - expected) > max(0.15, 2 / float(fps)):
            raise RuntimeError("Extended video failed duration/audio validation")
        result.replace(destination)
    return expected
