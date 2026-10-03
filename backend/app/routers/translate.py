"""Translate videos API: subtitles in another language, plus a draft avatar video of the translation."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..deps import get_current_user
from ..models import Movie, User
from ..services import movies, translate

router = APIRouter(prefix="/api/translate", tags=["translate"])

_ALLOWED = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".mp3", ".wav", ".m4a"}
_AUDIO_ONLY = {".mp3", ".wav", ".m4a"}
_CHUNK = 1024 * 1024


class ToMovieIn(BaseModel):
    title: str = Field(default="Translated video", max_length=200)
    lines: list[str] = Field(min_length=1, max_length=2000)
    avatar_id: str = Field(max_length=32)
    tts_voice_id: Optional[str] = Field(default=None, max_length=200)
    orientation: Literal["portrait", "landscape"] = "landscape"


@router.get("/languages")
def languages(user: User = Depends(get_current_user)):
    return translate.LANGUAGES


@router.post("")
def translate_video(
    file: UploadFile = File(...),
    language: str = Form(...),
    user: User = Depends(get_current_user),
):
    """Local Whisper (CPU) + Qwen; no credits. Can take several minutes for long files."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(status_code=400, detail="Upload an MP4, MOV, WEBM, MKV, M4V, MP3, WAV or M4A file.")
    if language not in translate.LANGUAGES:
        raise HTTPException(status_code=400, detail="Choose one of the listed languages.")
    folder = config.STORAGE_DIR / "translate"
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
        result = translate.translate_media(source, language)
    except RuntimeError as exc:
        source.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    (folder / f"{stem}.srt").write_text(result.pop("srt"), encoding="utf-8")
    (folder / f"{stem}.vtt").write_text(result.pop("vtt"), encoding="utf-8")
    result.update(
        video_url=f"/storage/translate/{source.name}", srt_url=f"/storage/translate/{stem}.srt",
        vtt_url=f"/storage/translate/{stem}.vtt", has_video=suffix not in _AUDIO_ONLY,
    )
    return result


@router.post("/to-movie", status_code=201)
def translation_to_movie(payload: ToMovieIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Draft scene-by-scene video where the avatar says the translated lines."""
    scripts = translate.split_scenes(payload.lines)
    if not scripts:
        raise HTTPException(status_code=422, detail="There is no text to turn into scenes.")
    if len(scripts) > movies.MAX_SCENES:
        raise HTTPException(status_code=422, detail=f"That is {len(scripts)} scenes; the limit is {movies.MAX_SCENES}. Use a shorter video.")
    scenes = [
        movies.clean_scene({"avatar_id": payload.avatar_id, "tts_voice_id": payload.tts_voice_id, "script": s})
        for s in scripts
    ]
    movie = Movie(user_id=user.id, title=payload.title.strip()[:200] or "Translated video", orientation=payload.orientation)
    movies.save_scenes(movie, scenes)
    db.add(movie)
    db.commit()
    return {"movie_id": movie.id, "scenes": len(scenes), "credits_estimate": movies.cost_estimate(scenes)}
