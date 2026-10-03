"""Auto clips API: upload a long video, get back short clips of its best moments."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import config
from ..deps import get_current_user
from ..models import User
from ..services import auto_clips

router = APIRouter(prefix="/api/auto-clips", tags=["auto-clips"])

_ALLOWED = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".mp3", ".wav", ".m4a"}
_CHUNK = 1024 * 1024


@router.post("")
def create_clips(
    file: UploadFile = File(...),
    clip_count: int = Form(default=3, ge=1, le=8),
    clip_seconds: int = Form(default=30, ge=15, le=90),
    user: User = Depends(get_current_user),
):
    """Runs locally (Whisper on CPU, Qwen on GPU, FFmpeg); no credits. Can take several minutes."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(status_code=400, detail="Upload an MP4, MOV, WEBM, MKV, M4V, MP3, WAV or M4A file.")
    folder = config.STORAGE_DIR / "auto_clips"
    folder.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    source = folder / f"{stem}_source{suffix}"
    limit = config.TRANSCRIPTION_MAX_UPLOAD_MB * 1024 * 1024
    written = 0
    with source.open("wb") as handle:
        while chunk := file.file.read(_CHUNK):
            written += len(chunk)
            if written > limit:
                handle.close()
                source.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File is larger than {config.TRANSCRIPTION_MAX_UPLOAD_MB} MB.")
            handle.write(chunk)
    try:
        result = auto_clips.make_clips(source, folder, stem, clip_count, clip_seconds)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        source.unlink(missing_ok=True)  # clips are kept; the big upload is not
    for clip in result["clips"]:
        clip["url"] = f"/storage/auto_clips/{clip.pop('file')}"
    return result
