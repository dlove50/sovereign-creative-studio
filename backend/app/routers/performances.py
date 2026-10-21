"""Multi-Performer Director API (duets, trios, choirs, dialogues).

GET    /api/performances/modes                               the five performance modes
POST   /api/performances                                     new performance with named performers
GET    /api/performances                                     your performances, newest first
GET    /api/performances/{id}                                project + director sheet
PATCH  /api/performances/{id}                                title, mode, stage, camera
DELETE /api/performances/{id}                                remove it and its files
POST   /api/performances/{id}/master                         upload the master song
POST   /api/performances/{id}/from-song                      use a Music Lab song (+ its split vocal)
POST   /api/performances/{id}/shared-vocal                   upload one vocal to split by hand-offs
PATCH  /api/performances/{id}/performers/{pid}               name, role, stage position, motion
POST   /api/performances/{id}/performers/{pid}/stem          upload this performer's vocal stem
POST   /api/performances/{id}/performers/{pid}/identity      upload this performer's identity picture
PUT    /api/performances/{id}/performers/{pid}/regions       replace their timeline regions
POST   /api/performances/{id}/analyze                        find each performer's voice in their stem
POST   /api/performances/{id}/handoffs                       hand parts of a shared vocal to performers
POST   /api/performances/{id}/drive-audio                    build each performer's lip-sync audio
GET    /api/performances/{id}/render-plan                    passes, cues, and what is still missing
GET    /api/performances/{id}/files/{name}                   a stored file (owner only)
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User
from ..services import music, performance_engine as pe, stems

router = APIRouter(prefix="/api/performances", tags=["performances"])

AUDIO_EXT = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
MAX_AUDIO_BYTES = 300 * 1024 * 1024
MAX_IMAGE_BYTES = 25 * 1024 * 1024

State = Literal["SINGING", "SPEAKING", "BACKGROUND_VOCAL", "LISTENING", "MOVING", "IDLE"]
Mode = Literal["alternating", "call_response", "harmony", "lead_background", "shared_stage"]


class CreateIn(BaseModel):
    title: str = Field(default="", max_length=120)
    performers: list[str] = Field(min_length=1, max_length=pe.MAX_PERFORMERS)
    mode: Mode = "alternating"


class Shot(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    shot: Literal["wide", "two_shot", "close_up", "alternating"]
    focus: str | None = None


class StageIn(BaseModel):
    prompt: str = Field(default="", max_length=1000)
    aspect: Literal["16:9", "9:16", "1:1"] = "16:9"


class PatchIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    mode: Mode | None = None
    stage: StageIn | None = None
    camera: list[Shot] | None = Field(default=None, max_length=500)


class Position(BaseModel):
    x: float = Field(ge=0, le=1)
    scale: float = Field(default=1.0, ge=0.3, le=2.0)
    facing: Literal["audience", "left", "right", "partner"] = "audience"


class Motion(BaseModel):
    sway: float = Field(ge=0, le=1)
    energy: float = Field(ge=0, le=1)


class PerformerPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    role: Literal["lead", "co_lead", "background", "actor"] | None = None
    voice_id: str | None = Field(default=None, max_length=80)
    stage: Position | None = None
    motion: Motion | None = None


class RegionIn(BaseModel):
    id: str | None = Field(default=None, max_length=32)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    state: State
    intensity: float = Field(default=0.6, ge=0, le=1)
    lyric: str = Field(default="", max_length=300)
    source: Literal["own", "shared"] = "own"


class RegionsIn(BaseModel):
    regions: list[RegionIn] = Field(max_length=pe.MAX_REGIONS)


class HandoffIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    performers: list[str] = Field(min_length=1, max_length=pe.MAX_PERFORMERS)
    state: State | None = None


class HandoffsIn(BaseModel):
    handoffs: list[HandoffIn] = Field(min_length=1, max_length=500)


class FromSongIn(BaseModel):
    song_id: str = Field(min_length=1, max_length=64)
    split_vocal: bool = True


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _owned(project_id: str, user: User) -> dict:
    try:
        project = pe.get(project_id)
    except pe.PerformanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if project is None or project["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Performance not found.")
    return project


def _url(project: dict, path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if p.parent == pe.media_dir(project["id"]):
        return f"/api/performances/{project['id']}/files/{p.name}"
    return None  # a file outside this performance (e.g. a Music Lab stem): served by its own feature


def _public(project: dict) -> dict:
    out = {k: v for k, v in project.items() if k != "user_id"}
    out["master_audio_url"] = _url(project, project.get("master_audio"))
    out["shared_vocal_url"] = _url(project, project.get("shared_vocal"))
    out["performers"] = [
        {**p, "stem_url": _url(project, p.get("stem")), "identity_url": _url(project, p.get("identity_image")),
         "drive_audio_url": _url(project, p.get("drive_audio"))}
        for p in project["performers"]
    ]
    out["sheet"] = pe.director_sheet(project) if project.get("duration") else []
    return out


def _save(project: dict) -> dict:
    try:
        return _public(pe.save(project))
    except pe.PerformanceError as exc:
        raise _bad(exc) from exc


def _store_upload(project: dict, upload: UploadFile, stem: str, allowed: set[str], limit: int) -> str:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Use one of: {', '.join(sorted(allowed))}.")
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail="That file is too large.")
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    folder = pe.media_dir(project["id"])
    for old in folder.glob(f"{stem}.*"):
        old.unlink(missing_ok=True)
    path = folder / f"{stem}{ext}"
    path.write_bytes(data)
    return str(path)


@router.get("/modes")
def modes(_user: User = Depends(get_current_user)):
    return {"modes": pe.MODES, "states": list(pe.STATES), "voiced": list(pe.VOICED)}


@router.post("", status_code=201)
def create(body: CreateIn, user: User = Depends(get_current_user)):
    try:
        return _public(pe.create(user.id, body.title, body.performers, body.mode))
    except pe.PerformanceError as exc:
        raise _bad(exc) from exc


@router.get("")
def list_all(user: User = Depends(get_current_user)):
    return [_public(p) for p in pe.list_for(user.id)]


@router.get("/{project_id}")
def read(project_id: str, user: User = Depends(get_current_user)):
    return _public(_owned(project_id, user))


@router.patch("/{project_id}")
def patch(project_id: str, body: PatchIn, user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    if body.title is not None:
        project["title"] = body.title.strip() or project["title"]
    if body.stage is not None:
        project["stage"].update(body.stage.model_dump())
    try:
        if body.mode is not None:
            pe.apply_mode(project, body.mode)
    except pe.PerformanceError as exc:
        raise _bad(exc) from exc
    if body.camera is not None:
        ids = {p["id"] for p in project["performers"]}
        if any(s.focus and s.focus not in ids for s in body.camera):
            raise HTTPException(status_code=400, detail="A shot focuses on an unknown performer.")
        project["camera"] = [s.model_dump() for s in sorted(body.camera, key=lambda s: s.start)]
    return _save(project)


@router.delete("/{project_id}", status_code=204)
def remove(project_id: str, user: User = Depends(get_current_user)):
    _owned(project_id, user)
    pe.delete(project_id)


@router.post("/{project_id}/master")
def upload_master(project_id: str, file: UploadFile = File(...), user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    project["master_audio"] = _store_upload(project, file, "master", AUDIO_EXT, MAX_AUDIO_BYTES)
    try:
        pe.set_duration_from(project, project["master_audio"])
    except pe.PerformanceError as exc:
        raise _bad(exc) from exc
    return _save(project)


@router.post("/{project_id}/from-song")
def from_song(project_id: str, body: FromSongIn, user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    try:
        song = music.get_song(body.song_id)
        if song is None:
            raise HTTPException(status_code=404, detail="Song not found.")
        project["master_audio"] = str(music.audio_path(body.song_id))
        pe.set_duration_from(project, project["master_audio"])
        if body.split_vocal:
            project["shared_vocal"] = str(stems.ensure_stems(body.song_id)["vocals"])
    except (music.MusicError, pe.PerformanceError) as exc:
        raise _bad(exc) from exc
    return _save(project)


@router.post("/{project_id}/shared-vocal")
def upload_shared_vocal(project_id: str, file: UploadFile = File(...), user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    project["shared_vocal"] = _store_upload(project, file, "shared-vocal", AUDIO_EXT, MAX_AUDIO_BYTES)
    return _save(project)


@router.patch("/{project_id}/performers/{performer_id}")
def patch_performer(project_id: str, performer_id: str, body: PerformerPatch, user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    try:
        p = pe.performer(project, performer_id)
    except pe.PerformanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if body.name is not None:
        p["name"] = body.name.strip()
    if body.role is not None:
        p["role"] = body.role
    if body.voice_id is not None:
        p["voice_id"] = body.voice_id or None
    if body.stage is not None:
        p["stage"] = body.stage.model_dump()
    if body.motion is not None:
        p["motion"].update(body.motion.model_dump())
    return _save(project)


@router.post("/{project_id}/performers/{performer_id}/stem")
def upload_stem(project_id: str, performer_id: str, file: UploadFile = File(...),
                user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    try:
        p = pe.performer(project, performer_id)
    except pe.PerformanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    p["stem"] = _store_upload(project, file, f"stem-{performer_id}", AUDIO_EXT, MAX_AUDIO_BYTES)
    return _save(project)


@router.post("/{project_id}/performers/{performer_id}/identity")
def upload_identity(project_id: str, performer_id: str, file: UploadFile = File(...),
                    user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    try:
        p = pe.performer(project, performer_id)
    except pe.PerformanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    p["identity_image"] = _store_upload(project, file, f"identity-{performer_id}", IMAGE_EXT, MAX_IMAGE_BYTES)
    return _save(project)


@router.put("/{project_id}/performers/{performer_id}/regions")
def put_regions(project_id: str, performer_id: str, body: RegionsIn, user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    try:
        pe.set_regions(project, performer_id, [r.model_dump() for r in body.regions])
    except pe.PerformanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _save(project)


@router.post("/{project_id}/analyze")
def analyze(project_id: str, user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    try:
        pe.analyze_stems(project)
    except pe.PerformanceError as exc:
        raise _bad(exc) from exc
    return _save(project)


@router.post("/{project_id}/handoffs")
def handoffs(project_id: str, body: HandoffsIn, user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    try:
        pe.assign_handoffs(project, [h.model_dump() for h in body.handoffs])
    except pe.PerformanceError as exc:
        raise _bad(exc) from exc
    return _save(project)


@router.post("/{project_id}/drive-audio")
def drive_audio(project_id: str, user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    try:
        pe.validate(project)
        for p in project["performers"]:
            pe.build_drive_audio(project, p["id"])
    except pe.PerformanceError as exc:
        raise _bad(exc) from exc
    return _save(project)


@router.get("/{project_id}/render-plan")
def render_plan(project_id: str, user: User = Depends(get_current_user)):
    return pe.render_plan(_owned(project_id, user))


@router.get("/{project_id}/files/{name}")
def file(project_id: str, name: str, user: User = Depends(get_current_user)):
    project = _owned(project_id, user)
    folder = pe.media_dir(project["id"])
    path = (folder / name).resolve()
    if path.parent != folder.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path)
