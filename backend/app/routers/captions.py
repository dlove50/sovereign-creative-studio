"""Captions API: burn captions into a finished video that already lives in storage."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..deps import get_current_user
from ..models import User
from ..services import captions
from ..services.transcription import resolve_storage_url

router = APIRouter(prefix="/api/captions", tags=["captions"])

_VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


class CaptionIn(BaseModel):
    video_url: str = Field(max_length=512)


@router.post("")
def caption_video(payload: CaptionIn, user: User = Depends(get_current_user)):
    """Runs on the CPU (Whisper + FFmpeg), no credits. Sync def so FastAPI uses a worker thread."""
    if Path(payload.video_url).suffix.lower() not in _VIDEO_SUFFIXES:
        raise HTTPException(status_code=400, detail="Pick a video file.")
    try:
        source = resolve_storage_url(payload.video_url)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail="That video was not found.") from exc
    folder = config.STORAGE_DIR / "captioned"
    folder.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    out = folder / f"{stem}.mp4"
    try:
        result = captions.add_captions(source, out)
    except RuntimeError as exc:
        out.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    (folder / f"{stem}.srt").write_text(result["srt"], encoding="utf-8")
    return {"video_url": f"/storage/captioned/{out.name}", "srt_url": f"/storage/captioned/{stem}.srt", "captions": result["captions"]}
