"""Owner-controlled cloud studio. Local generation routes remain unchanged."""
from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError, model_validator

from ..deps import require_admin
from ..services import cloud_media as cloud
from ..services.integrations import list_providers

router = APIRouter(prefix="/api/cloud", tags=["cloud-media"], dependencies=[Depends(require_admin)])
UPLOAD_OPERATIONS = {"voice-changer", "transcribe", "dubbing", "isolate"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".webm"}


class CloudRequest(BaseModel):
    request_id: UUID
    operation: Literal["avatar-video", "tts", "sound-effects", "voice-changer", "transcribe", "dubbing", "isolate"]
    accept_charges: Literal[True]
    title: str = Field(default="", max_length=120)
    text: str = Field(default="", max_length=5000)
    voice_id: str = Field(default="", max_length=200, pattern=r"^[A-Za-z0-9_-]*$")
    avatar_id: str = Field(default="", max_length=200, pattern=r"^[A-Za-z0-9_-]*$")
    engine: Literal["avatar_iv", "avatar_v", "avatar_iii"] = "avatar_iv"
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"
    duration_seconds: float = Field(default=5, ge=0.5, le=30)
    loop: bool = False
    target_lang: str = Field(default="en", pattern=r"^[a-z]{2,3}$")

    @model_validator(mode="after")
    def required_inputs(self):
        self.text = self.text.strip()
        if self.operation in {"tts", "sound-effects", "avatar-video"} and not self.text:
            raise ValueError("Enter text for this operation.")
        if self.operation in {"tts", "voice-changer"} and not self.voice_id:
            raise ValueError("Choose a voice first.")
        if self.operation == "avatar-video" and not self.avatar_id:
            raise ValueError("Choose a HeyGen avatar look first.")
        return self


@router.get("/status")
def status():
    return {"providers": [p for p in list_providers() if p["id"] in {"heygen", "elevenlabs"}],
            "output_directory": str(cloud.root().resolve()), "max_upload_mb": cloud.MAX_UPLOAD // 1024 // 1024}


@router.get("/{provider}/catalog/{kind}")
def catalog(provider: Literal["heygen", "elevenlabs"], kind: Literal["voices", "avatars"],
            token: str = Query(default="", max_length=4096),
            ownership: Literal["public", "private"] = "public", search: str = Query(default="", max_length=200)):
    return cloud.catalog(provider, kind, token, ownership, search)


@router.get("/jobs")
def jobs():
    return [cloud.public(job) for job in cloud.history()]


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    return cloud.public(cloud.read(job_id))


@router.post("/jobs", status_code=202)
def submit(payload: CloudRequest, background: BackgroundTasks):
    if payload.operation in UPLOAD_OPERATIONS:
        raise HTTPException(400, "This operation requires an uploaded audio or video file.")
    data = payload.model_dump(mode="json")
    job, created = cloud.create(data)
    if created:
        background.add_task(cloud.execute, job["id"], data)
    return cloud.public(job)


@router.post("/upload-jobs", status_code=202)
async def submit_upload(background: BackgroundTasks, payload: str = Form(...), file: UploadFile = File(...)):
    try:
        parsed = CloudRequest.model_validate_json(payload)
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid cloud request. Check the operation, voice and target language.") from None
    if parsed.operation not in UPLOAD_OPERATIONS:
        raise HTTPException(400, "This operation uses text rather than an upload.")
    suffix = Path(file.filename or "").suffix.lower()
    allowed = AUDIO_SUFFIXES | ({".mp4", ".mov", ".mkv"} if parsed.operation in {"dubbing", "transcribe"} else set())
    if suffix not in allowed:
        raise HTTPException(400, "Choose a supported audio file (or video for transcription/dubbing).")
    try:
        content = await file.read(cloud.MAX_UPLOAD + 1)
    finally:
        await file.close()
    if not content or len(content) > cloud.MAX_UPLOAD:
        raise HTTPException(413, "Upload must contain data and be no larger than 100 MB.")
    data = parsed.model_dump(mode="json")
    job, created = cloud.create(data, content, suffix)
    if created:
        background.add_task(cloud.execute, job["id"], data, suffix)
    return cloud.public(job)


@router.post("/jobs/{job_id}/refresh")
def refresh(job_id: str):
    return cloud.public(cloud.refresh(job_id))


@router.get("/jobs/{job_id}/files/{name}")
def download(job_id: str, name: str):
    job = cloud.read(job_id)
    if name not in job["files"] or Path(name).name != name:
        raise HTTPException(404, "Cloud output not found")
    path = cloud.folder(job_id) / name
    if not path.is_file():
        raise HTTPException(404, "Cloud output file is missing")
    return FileResponse(path, filename=name)
