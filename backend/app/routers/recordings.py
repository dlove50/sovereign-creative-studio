"""Screen recordings: the browser records the screen (and microphone), this saves the clip to the user's library.

The recording arrives as WebM (MediaRecorder has no duration or seek data), so it is converted to a standard
H.264/AAC MP4 that plays everywhere and can be used in videos and interactive lessons. No credits, no GPU.
"""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..deps import get_current_user
from ..models import Project, User, VideoGeneration
from ..services.audio_merge import _ffmpeg

router = APIRouter(prefix="/api/recordings", tags=["recordings"])

_ALLOWED = {".webm", ".mp4", ".mkv", ".mov"}
_CHUNK = 1024 * 1024
MAX_MB = 512
MAX_SECONDS = 3 * 60 * 60


def _probe(path: Path, ffmpeg: str) -> dict:
    """Stream facts via ffmpeg itself (ffprobe may not sit next to it): video stream present, size, audio present."""
    ffprobe = str(Path(ffmpeg).with_name("ffprobe.exe" if ffmpeg.lower().endswith(".exe") else "ffprobe"))
    try:
        raw = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(path)],
                             capture_output=True, text=True, timeout=60, check=True).stdout
        return json.loads(raw)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="That recording could not be read.") from exc


def _library_project(db: Session, user: User) -> str:
    project_id = uuid.uuid5(uuid.NAMESPACE_URL, f"sovereign:screen-recordings:{user.id}").hex
    if db.get(Project, project_id) is None:
        db.add(Project(id=project_id, user_id=user.id, name="Screen recordings",
                       description="Clips recorded from your screen in Sovereign."))
        db.flush()
    return project_id


@router.post("", status_code=201)
def save_recording(
    file: UploadFile = File(...),
    title: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Sync def: FastAPI runs it in a worker thread, so the conversion does not block other requests."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(status_code=400, detail="Upload a WebM or MP4 screen recording.")
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        raise HTTPException(status_code=503, detail="FFmpeg was not found, so recordings cannot be converted.")
    video_id = uuid.uuid4().hex
    folder = config.STORAGE_DIR / "videos"
    folder.mkdir(parents=True, exist_ok=True)
    target, poster = folder / f"{video_id}.mp4", folder / f"{video_id}-poster.jpg"
    with tempfile.TemporaryDirectory(prefix="recording-") as tmp:
        source = Path(tmp) / f"raw{suffix}"
        limit, written = MAX_MB * 1024 * 1024, 0
        with source.open("wb") as handle:
            while chunk := file.file.read(_CHUNK):
                written += len(chunk)
                if written > limit:
                    raise HTTPException(status_code=413, detail=f"A recording can be up to {MAX_MB} MB.")
                handle.write(chunk)
        if written == 0:
            raise HTTPException(status_code=422, detail="The recording is empty.")
        facts = _probe(source, ffmpeg)
        if not any(s.get("codec_type") == "video" for s in facts.get("streams", [])):
            raise HTTPException(status_code=422, detail="That file has no video in it.")
        has_audio = any(s.get("codec_type") == "audio" for s in facts.get("streams", []))
        command = [ffmpeg, "-y", "-v", "error", "-i", str(source), "-t", str(MAX_SECONDS),
                   "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        command += ["-c:a", "aac", "-b:a", "128k"] if has_audio else ["-an"]
        try:
            subprocess.run(command + [str(target)], capture_output=True, text=True, timeout=1800, check=True)
            subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(target), "-frames:v", "1", "-vf", "scale=640:-2", str(poster)],
                           capture_output=True, text=True, timeout=120, check=True)
            converted = _probe(target, ffmpeg)
        except (OSError, subprocess.SubprocessError) as exc:
            target.unlink(missing_ok=True)
            poster.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail="The recording could not be converted to MP4.") from exc
    video = next((s for s in converted.get("streams", []) if s.get("codec_type") == "video"), {})
    try:
        seconds = float(video.get("duration") or 0)
    except ValueError:
        seconds = 0.0
    if seconds <= 0:
        timing = subprocess.run([ffmpeg, "-i", str(target)], capture_output=True, text=True).stderr
        marker = timing.find("Duration:")
        if marker >= 0:
            h, m, s = timing[marker + 10:marker + 21].split(":")
            seconds = int(h) * 3600 + int(m) * 60 + float(s)
    name = " ".join(title.split())[:120] or f"Screen recording {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    project_id = _library_project(db, user)
    db.add(VideoGeneration(
        id=video_id, user_id=user.id, project_id=project_id, source_image_url=f"/storage/videos/{poster.name}",
        mode="video_to_video", provider="screen_recording", prompt=name, motion_preset="recording",
        duration_seconds=max(1, math.ceil(seconds)), credits_cost=0, status="completed",
        result_url=f"/storage/videos/{target.name}", file_size_bytes=target.stat().st_size,
        completed_at=datetime.now(timezone.utc)))
    db.commit()
    return {"id": video_id, "title": name, "result_url": f"/storage/videos/{target.name}",
            "poster_url": f"/storage/videos/{poster.name}", "duration_seconds": round(seconds, 1),
            "has_audio": has_audio, "project_id": project_id, "size_bytes": target.stat().st_size}
