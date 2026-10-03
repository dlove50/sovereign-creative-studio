"""Speech cleanup API: upload a video/audio file, get back a version without long pauses/fillers."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import config
from ..deps import get_current_user
from ..models import User
from ..services import speech_cleanup

router = APIRouter(prefix="/api/speech-cleanup", tags=["speech-cleanup"])

_ALLOWED = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".mp3", ".wav", ".m4a"}
_AUDIO_ONLY = {".mp3", ".wav", ".m4a"}
_CHUNK = 1024 * 1024


@router.post("")
def clean_speech(
    file: UploadFile = File(...),
    remove_pauses: bool = Form(default=True),
    remove_fillers: bool = Form(default=True),
    user: User = Depends(get_current_user),
):
    """Runs on the CPU (FFmpeg + Whisper); no credits. Sync def: FastAPI uses a worker thread."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(status_code=400, detail="Upload an MP4, MOV, WEBM, MKV, M4V, MP3, WAV or M4A file.")
    if not (remove_pauses or remove_fillers):
        raise HTTPException(status_code=400, detail="Choose at least one thing to remove.")
    folder = config.STORAGE_DIR / "speech_cleanup"
    folder.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex
    source = folder / f"{stem}_original{suffix}"
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
    out = folder / f"{stem}_clean{'.m4a' if suffix in _AUDIO_ONLY else '.mp4'}"
    try:
        result = speech_cleanup.clean(source, out, remove_pauses=remove_pauses, remove_fillers=remove_fillers)
    except RuntimeError as exc:
        out.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**result, "output_url": f"/storage/speech_cleanup/{out.name}", "filename": file.filename}
