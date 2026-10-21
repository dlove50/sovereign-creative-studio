"""Universal AI Enhance API: Select media -> Enhance -> Compare -> Adjust -> Apply.

GET    /api/enhance/operations                 every enhancement, its settings, and whether it is installed
POST   /api/enhance/jobs                       upload a file and enhance it (multipart: file, ops JSON, name)
POST   /api/enhance/jobs/from-library          enhance media already in the library (by /storage URL)
GET    /api/enhance/jobs                       your enhancements, newest first
GET    /api/enhance/jobs/{id}                  progress and outputs
GET    /api/enhance/jobs/{id}/source           the untouched original (for comparison)
GET    /api/enhance/jobs/{id}/outputs/{n}      an enhanced version
POST   /api/enhance/jobs/{id}/cancel           stop it
POST   /api/enhance/jobs/{id}/apply            choose the version to use (the original is kept)
DELETE /api/enhance/jobs/{id}                  remove the enhancement and its outputs (never the library original)
GET    /api/enhance/presets                    your saved presets
POST   /api/enhance/presets                    save a preset
DELETE /api/enhance/presets/{id}               delete a preset
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User
from ..services import enhance

router = APIRouter(prefix="/api/enhance", tags=["enhance"])

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


class OpIn(BaseModel):
    op: str = Field(min_length=1, max_length=40)
    params: dict[str, float] = Field(default_factory=dict)


class LibraryJobIn(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    ops: list[OpIn] = Field(min_length=1, max_length=enhance.MAX_OPS)


class ApplyIn(BaseModel):
    index: int = Field(default=0, ge=0, le=10)


class PresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["image", "audio", "video"]
    ops: list[OpIn] = Field(min_length=1, max_length=enhance.MAX_OPS)


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _owned(job_id: str, user: User) -> dict[str, Any]:
    try:
        job = enhance.get_job(job_id)
    except enhance.EnhanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if job is None or job["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Enhancement not found.")
    return job


def _public(job: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in job.items() if k not in ("user_id", "source")}
    out["source_url"] = f"/api/enhance/jobs/{job['id']}/source"
    out["outputs"] = [{"label": o["label"], "kind": o["kind"], "url": f"/api/enhance/jobs/{job['id']}/outputs/{i}"}
                      for i, o in enumerate(job.get("outputs", []))]
    return out


@router.get("/operations")
def operations(_user: User = Depends(get_current_user)):
    return {"operations": enhance.catalog()}


@router.post("/jobs", status_code=202)
def upload_job(file: UploadFile = File(...), ops: str = Form(...), name: str = Form(default=""),
               user: User = Depends(get_current_user)):
    try:
        parsed = [OpIn(**o).model_dump() for o in json.loads(ops)]
        kind = enhance.kind_of(file.filename or "")
    except (ValueError, TypeError) as exc:
        raise _bad(exc) from exc
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="That file is too large.")
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    try:
        enhance.validate_ops(kind, parsed)  # fail before writing anything
    except enhance.EnhanceError as exc:
        raise _bad(exc) from exc
    job_id = uuid.uuid4().hex[:12]
    source = enhance.job_dir(job_id) / f"original{Path(file.filename or '').suffix.lower()}"
    source.write_bytes(data)
    try:
        return _public(enhance.create_job(user.id, source, name or file.filename or "Media", parsed, job_id=job_id))
    except enhance.EnhanceError as exc:
        enhance.delete_job(job_id)
        raise _bad(exc) from exc


@router.post("/jobs/from-library", status_code=202)
def library_job(body: LibraryJobIn, user: User = Depends(get_current_user)):
    try:
        source = enhance.resolve_storage_path(body.url)
        return _public(enhance.create_job(user.id, source, source.name, [o.model_dump() for o in body.ops]))
    except enhance.EnhanceError as exc:
        raise _bad(exc) from exc


@router.get("/jobs")
def jobs(user: User = Depends(get_current_user)):
    return [_public(j) for j in enhance.list_jobs(user.id)]


@router.get("/jobs/{job_id}")
def job(job_id: str, user: User = Depends(get_current_user)):
    return _public(_owned(job_id, user))


@router.get("/jobs/{job_id}/source")
def source(job_id: str, user: User = Depends(get_current_user)):
    path = Path(_owned(job_id, user)["source"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="The original is no longer available.")
    return FileResponse(path)


@router.get("/jobs/{job_id}/outputs/{index}")
def output(job_id: str, index: int, user: User = Depends(get_current_user)):
    outputs = _owned(job_id, user).get("outputs", [])
    if not 0 <= index < len(outputs) or not Path(outputs[index]["path"]).is_file():
        raise HTTPException(status_code=404, detail="Output not found.")
    return FileResponse(outputs[index]["path"])


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str, user: User = Depends(get_current_user)):
    _owned(job_id, user)
    enhance.cancel(job_id)
    return {"cancelling": True}


@router.post("/jobs/{job_id}/apply")
def apply(job_id: str, body: ApplyIn, user: User = Depends(get_current_user)):
    _owned(job_id, user)
    try:
        return _public(enhance.apply(job_id, body.index))
    except enhance.EnhanceError as exc:
        raise _bad(exc) from exc


@router.delete("/jobs/{job_id}", status_code=204)
def delete(job_id: str, user: User = Depends(get_current_user)):
    _owned(job_id, user)
    enhance.delete_job(job_id)


@router.get("/presets")
def presets(user: User = Depends(get_current_user)):
    return enhance.list_presets(user.id)


@router.post("/presets", status_code=201)
def save_preset(body: PresetIn, user: User = Depends(get_current_user)):
    try:
        return enhance.save_preset(user.id, body.name, body.kind, [o.model_dump() for o in body.ops])
    except enhance.EnhanceError as exc:
        raise _bad(exc) from exc


@router.delete("/presets/{preset_id}")
def delete_preset(preset_id: str, user: User = Depends(get_current_user)):
    return enhance.delete_preset(user.id, preset_id)
