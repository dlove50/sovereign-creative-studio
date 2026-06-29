"""Audio-merge endpoint for Quick Chain Phase 2.2 (voice selection + preview).

GET  /api/audio-merge/readiness  — capability detection (FFmpeg + Piper, voices list).
POST /api/audio-merge/preview    — generate a TTS WAV preview, return audio URL.
POST /api/audio-merge            — merge TTS audio onto an existing local video.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..config import STORAGE_DIR
from ..deps import get_current_user
from ..models import User
from ..services.audio_merge import (
    audio_merge_readiness,
    generate_voice_preview,
    merge_tts_onto_video,
)

router = APIRouter(prefix="/api/audio-merge", tags=["audio_merge"])


class AudioMergeIn(BaseModel):
    source_video_url: str
    tts_text: str | None = None
    voice_id: str | None = None


class AudioMergeOut(BaseModel):
    result_url: str
    output_url: str
    file_size_bytes: int
    voice_id: str | None = None
    status: str = "completed"


class VoicePreviewIn(BaseModel):
    tts_text: str
    voice_id: str | None = None


class VoicePreviewOut(BaseModel):
    audio_url: str
    output_url: str
    file_size_bytes: int
    voice_id: str | None = None
    status: str = "completed"


@router.get("/readiness")
def get_readiness(_user: User = Depends(get_current_user)):
    return audio_merge_readiness()


@router.post("/preview", response_model=VoicePreviewOut)
def create_voice_preview(
    body: VoicePreviewIn,
    _user: User = Depends(get_current_user),
):
    if not body.tts_text or not body.tts_text.strip():
        raise HTTPException(status_code=422, detail="tts_text is required.")
    try:
        wav_path = generate_voice_preview(body.tts_text.strip(), voice_id=body.voice_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    rel_out = wav_path.relative_to(STORAGE_DIR)
    audio_url = f"/storage/{rel_out.as_posix()}"
    size = wav_path.stat().st_size
    return VoicePreviewOut(
        audio_url=audio_url,
        output_url=audio_url,
        file_size_bytes=size,
        voice_id=body.voice_id,
        status="completed",
    )


@router.post("", response_model=AudioMergeOut)
def create_audio_merge(
    body: AudioMergeIn,
    _user: User = Depends(get_current_user),
):
    if not body.tts_text or not body.tts_text.strip():
        raise HTTPException(status_code=422, detail="tts_text is required.")

    rel = body.source_video_url.lstrip("/").removeprefix("storage/")
    source_path = STORAGE_DIR / rel
    if not source_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Source video not found: {body.source_video_url}",
        )

    try:
        out_path = merge_tts_onto_video(
            body.source_video_url,
            body.tts_text.strip(),
            voice_id=body.voice_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    rel_out = out_path.relative_to(STORAGE_DIR)
    result_url = f"/storage/{rel_out.as_posix()}"
    size = out_path.stat().st_size

    return AudioMergeOut(
        result_url=result_url,
        output_url=result_url,
        file_size_bytes=size,
        voice_id=body.voice_id,
        status="completed",
    )
