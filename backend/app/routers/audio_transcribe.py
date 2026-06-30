"""POST /api/audio/transcribe — transcribe microphone audio for prompt input.

No credits are charged. No database record is created.
Used by the Whisper Flow voice input UI so users can speak their prompts.
Accepts webm/wav/mp3/m4a blobs from the browser MediaRecorder API.
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..config import TRANSCRIPTION_MODEL_NAME
from ..services.transcription import get_transcription_adapter

router = APIRouter(prefix="/api/audio", tags=["audio"])

_ALLOWED_EXTENSIONS = {".webm", ".wav", ".mp3", ".m4a", ".ogg"}
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/transcribe")
def transcribe_audio_prompt(file: UploadFile = File(...)) -> dict:
    """Transcribe a microphone audio blob and return the transcript text.

    No credits are charged — this is prompt input, not a content generation job.
    Returns: { text, language, duration_seconds, error }
    """
    ext = Path(file.filename or "audio.webm").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format {ext!r}. Supported: webm, wav, mp3, m4a.",
        )

    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large (max 10 MB).")

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext or ".webm", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(data)

        adapter = get_transcription_adapter()
        t0 = time.monotonic()
        result = adapter.transcribe(source_path=tmp_path, model_name=TRANSCRIPTION_MODEL_NAME)
        elapsed = round(time.monotonic() - t0, 2)

        return {
            "text": result.transcript_text or "",
            "language": result.detected_language,
            "duration_seconds": elapsed,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 — soft error so caller can handle gracefully
        return {
            "text": "",
            "language": None,
            "duration_seconds": 0,
            "error": str(exc),
        }
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
