"""Private Motion Studio endpoints, separate from existing video generation."""
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, Path as PathParam
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ..deps import require_admin
from ..models import User
from ..services import motion_studio as studio

router = APIRouter(prefix="/api/motion-studio", tags=["motion-studio"])


def owned(job_id: str, user: User) -> dict:
    job = studio.read(job_id)
    if job["user_id"] != user.id:
        raise HTTPException(404, "Motion project not found")
    return job


@router.get("/status")
def status(user: User = Depends(require_admin)):
    return studio.readiness()


@router.get("/jobs")
def history(user: User = Depends(require_admin)):
    return studio.history(user.id)


@router.post("/jobs", status_code=202)
async def upload(background: BackgroundTasks, request_id: UUID = Form(...), title: str = Form("", max_length=120),
                 start: float = Form(0, ge=0, le=86400), seconds: float = Form(30, ge=2, le=30),
                 file: UploadFile = File(...), user: User = Depends(require_admin)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".mp4", ".mov"}:
        await file.close()
        raise HTTPException(422, "Choose an MP4 or MOV video.")
    try:
        content = await file.read(studio.MAX_UPLOAD + 1)
    finally:
        await file.close()
    if not content or len(content) > studio.MAX_UPLOAD:
        raise HTTPException(413, "Choose a nonempty video no larger than 200 MB.")
    job, created = studio.create(str(request_id), user.id, title, content, suffix, start, seconds)
    if created:
        background.add_task(studio.prepare, job["id"])
    return studio.public(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, user: User = Depends(require_admin)):
    return studio.public(owned(job_id, user))


@router.post("/jobs/{job_id}/characters/{slot}")
async def character(job_id: str, slot: int = PathParam(ge=1, le=2), file: UploadFile = File(...), user: User = Depends(require_admin)):
    owned(job_id, user)
    try:
        content = await file.read(30 * 1024 * 1024 + 1)
    finally:
        await file.close()
    if not content or len(content) > 30 * 1024 * 1024:
        raise HTTPException(413, "Choose a reference image no larger than 30 MB.")
    return studio.public(studio.add_character(job_id, content, int(slot)))


@router.post("/jobs/{job_id}/approve")
def approve(job_id: str, user: User = Depends(require_admin)):
    owned(job_id, user)
    return studio.public(studio.approve(job_id))


@router.delete("/jobs/{job_id}/characters/{slot}")
def remove_character(job_id: str, slot: int = PathParam(ge=1, le=2), user: User = Depends(require_admin)):
    owned(job_id, user)
    with studio.LOCK:
        job = studio.read(job_id)
        if job["status"] in {"preparing", "submitting", "rendering", "exporting"}:
            raise HTTPException(409, "Wait for the current operation to finish before changing characters.")
        name = f"character-{slot}.jpg"
        job["characters"] = [value for value in job["characters"] if value != slot]
        job["files"] = [value for value in job["files"] if value != name]
        (studio.folder(job_id) / name).unlink(missing_ok=True)
        return studio.public(studio.save(job))


class RenderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    accept_charges: Literal[True]
    prompt: str = Field(default="", max_length=6000)
    scene: str = Field(default="", max_length=2000)
    draft_id: UUID | None = None


@router.post("/jobs/{job_id}/render/{kind}", status_code=202)
def render(job_id: str, kind: Literal["draft", "final"], payload: RenderIn, background: BackgroundTasks,
           user: User = Depends(require_admin)):
    owned(job_id, user)
    job, created = studio.begin(job_id, str(payload.request_id), kind, payload.prompt, payload.scene,
                                str(payload.draft_id) if payload.draft_id else None)
    if created:
        background.add_task(studio.submit, job_id, str(payload.request_id))
    return studio.public(job)


@router.post("/jobs/{job_id}/refresh")
def refresh(job_id: str, user: User = Depends(require_admin)):
    owned(job_id, user)
    return studio.public(studio.refresh(job_id))


@router.get("/jobs/{job_id}/files/{name}")
def file(job_id: str, name: str, user: User = Depends(require_admin)):
    job = owned(job_id, user)
    if Path(name).name != name or name not in job["files"]:
        raise HTTPException(404, "Motion file not found")
    path = studio.folder(job_id) / name
    if not path.is_file():
        raise HTTPException(404, "Motion file not found")
    return FileResponse(path, filename=name)
