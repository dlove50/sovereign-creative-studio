import os

from fastapi import APIRouter
import httpx

from .. import config
from ..config import (
    COMFYUI_BASE_URL,
    COPY_BACKEND,
    GENERATOR_BACKEND,
    OPENAI_API_KEY,
    PRODUCT_SCENE_BACKEND,
    STORAGE_DIR,
    VIDEO_BACKEND,
)
from ..schemas import StatusOut
from ..services.transcription import transcription_readiness

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status", response_model=StatusOut)
def status():
    """A single summary of how the backend is configured, for the status page."""
    comfyui_configured = (
        GENERATOR_BACKEND == "comfyui"
        or PRODUCT_SCENE_BACKEND == "comfyui"
        or VIDEO_BACKEND == "comfyui"
    )
    comfyui_reachable = False
    comfyui_error = None
    if comfyui_configured:
        try:
            resp = httpx.get(f"{COMFYUI_BASE_URL.rstrip('/')}/system_stats", timeout=2.0)
            resp.raise_for_status()
            comfyui_reachable = True
        except Exception as exc:  # noqa: BLE001 - status endpoint should report, not fail.
            comfyui_error = str(exc)
    transcription = transcription_readiness()

    return StatusOut(
        status="ok",
        generator_backend=GENERATOR_BACKEND,
        product_scene_backend=PRODUCT_SCENE_BACKEND,
        product_scene_model=config.PRODUCT_SCENE_MODEL or "legacy/default",
        product_scene_mode=config.COMFYUI_PRODUCT_SCENE_MODE,
        copy_backend=COPY_BACKEND,
        video_backend=VIDEO_BACKEND,
        video_engine=config.COMFYUI_VIDEO_ENGINE,
        transcription_backend=str(transcription["backend"]),
        transcription_available=bool(transcription["available"]),
        transcription_ffmpeg_available=bool(transcription["ffmpeg_available"]),
        transcription_faster_whisper_available=bool(
            transcription["faster_whisper_available"]
        ),
        transcription_model_name=str(transcription["model_name"]),
        transcription_model_dir=str(transcription["model_dir"]),
        transcription_device=str(transcription["device"]),
        transcription_compute_type=str(transcription["compute_type"]),
        transcription_message=str(transcription["message"]),
        comfyui_base_url=COMFYUI_BASE_URL,
        comfyui_configured=comfyui_configured,
        comfyui_reachable=comfyui_reachable,
        comfyui_error=comfyui_error,
        openai_configured=bool(OPENAI_API_KEY),
        storage_path=str(STORAGE_DIR),
        storage_writable=os.access(STORAGE_DIR, os.W_OK),
    )
