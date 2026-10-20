"""Import existing footage as completed project videos, without generation or credits."""
import math
import json
import subprocess
import uuid
from pathlib import Path

from fastapi import UploadFile

from .. import config
from .music_playback import find_ffmpeg_tool

VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
MAX_BYTES = 500 * 1024 * 1024


def import_video(upload: UploadFile) -> tuple[str, float, int]:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in VIDEO_SUFFIXES:
        raise ValueError("Choose an MP4, MOV, WEBM, MKV, AVI or M4V video.")
    ffmpeg = find_ffmpeg_tool("ffmpeg")
    ffprobe = find_ffmpeg_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ValueError("FFmpeg is unavailable. Video import cannot convert this file.")
    folder = config.STORAGE_DIR / "videos"
    folder.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex
    source = folder / f".import-{identifier}{suffix}"
    target = folder / f"{identifier}.mp4"
    try:
        size = 0
        with source.open("wb") as stream:
            while data := upload.file.read(1024 * 1024):
                size += len(data)
                if size > MAX_BYTES:
                    raise ValueError("This video is larger than 500 MB.")
                stream.write(data)
        if not size:
            raise ValueError("This video file is empty.")
        info = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(source)],
            capture_output=True, text=True, timeout=30, check=False,
        )
        try:
            metadata = json.loads(info.stdout)
            duration = float(metadata.get("format", {}).get("duration", 0))
            has_video = any(s.get("codec_type") == "video" for s in metadata.get("streams", []))
        except (ValueError, TypeError):
            raise ValueError("Could not read this video. Try exporting it as an MP4.") from None
        if info.returncode or not has_video or not math.isfinite(duration) or duration <= 0:
            raise ValueError("This file does not contain a playable video.")
        result = subprocess.run(
            [ffmpeg, "-v", "error", "-y", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
             "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
             "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(target)],
            capture_output=True, timeout=600, check=False,
        )
        if result.returncode or not target.is_file() or not target.stat().st_size:
            raise ValueError("This video could not be converted. Try exporting it as an MP4.")
        return f"/storage/videos/{target.name}", duration, target.stat().st_size
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        source.unlink(missing_ok=True)
