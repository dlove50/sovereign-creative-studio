"""Video agent API: write a spoken script from a plain-language request."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from ..deps import get_current_user
from ..models import CinematicPlan, CinematicProduction, VideoGeneration, User
from ..config import STORAGE_DIR
from ..services.cinematic_assembly import assemble_clips
from ..services.source_validation import validate_source_media_url, VIDEO_EXTS
from ..services import video_agent
from ..services import cinematic_planner

router = APIRouter(prefix="/api/video-agent", tags=["video-agent"])


class ScriptIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=8000)
    seconds: int = Field(default=30, ge=10, le=180)


class ScriptOut(BaseModel):
    title: str
    script: str
    model: str
    target_words: int


@router.post("/script", response_model=ScriptOut)
def write_script(payload: ScriptIn, user: User = Depends(get_current_user)):
    """Runs local Qwen (no credits). Sync def: FastAPI runs it in a worker thread."""
    try:
        return video_agent.write_script(payload.prompt, payload.seconds)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/plan", response_model=cinematic_planner.PlanOut)
def write_plan(payload: ScriptIn, user: User = Depends(get_current_user)):
    """Return a validated cinematic plan for review, without creating media jobs."""
    try:
        return cinematic_planner.write_plan(payload.prompt, payload.seconds)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class SavedPlanIn(ScriptIn):
    model_config = ConfigDict(extra="forbid")
    plan: cinematic_planner.PlanOut

    @model_validator(mode="after")
    def exact_duration(self):
        if sum(shot.duration_seconds for shot in self.plan.shots) != self.seconds:
            raise ValueError("Shot durations must total the requested seconds")
        return self


class SavedPlanUpdate(SavedPlanIn):
    revision: int = Field(ge=1)


class SavedPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    prompt: str
    seconds: int
    plan: cinematic_planner.PlanOut
    revision: int
    created_at: datetime
    updated_at: datetime


@router.post("/plans", response_model=SavedPlanOut, status_code=201)
def save_plan(payload: SavedPlanIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = CinematicPlan(user_id=user.id, prompt=payload.prompt, seconds=payload.seconds,
                        plan=payload.plan.model_dump(), revision=1)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/plans", response_model=list[SavedPlanOut])
def list_plans(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(select(CinematicPlan).where(CinematicPlan.user_id == user.id)
                      .order_by(CinematicPlan.updated_at.desc())).all()


def _owned_plan(plan_id: str, db: Session, user: User):
    row = db.get(CinematicPlan, plan_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Cinematic plan not found")
    return row


@router.get("/plans/{plan_id}", response_model=SavedPlanOut)
def load_plan(plan_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _owned_plan(plan_id, db, user)


@router.put("/plans/{plan_id}", response_model=SavedPlanOut)
def update_plan(plan_id: str, payload: SavedPlanUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _owned_plan(plan_id, db, user)
    result = db.execute(update(CinematicPlan).where(
        CinematicPlan.id == plan_id, CinematicPlan.user_id == user.id,
        CinematicPlan.revision == payload.revision,
    ).values(prompt=payload.prompt, seconds=payload.seconds, plan=payload.plan.model_dump(),
             revision=payload.revision + 1, updated_at=datetime.now(timezone.utc)))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This plan changed in another session. Reload it before saving your edits.")
    db.commit()
    return _owned_plan(plan_id, db, user)


class AttachShotIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    video_id: str = Field(min_length=1, max_length=64)


class AssembleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    retry: bool = False


def _production_out(plan, production):
    links = production.attachments if production else {}
    return {"plan_id": plan.id, "revision": plan.revision,
            "status": production.status if production else "draft",
            "shots": [{"shot_id": shot["id"], "video_id": links.get(shot["id"])} for shot in plan.plan["shots"]],
            "result_url": production.result_url if production else None,
            "error": production.error if production else None}


def _current_production(plan, db):
    row = db.get(CinematicProduction, (plan.id, plan.revision))
    if row is None:
        row = CinematicProduction(plan_id=plan.id, revision=plan.revision, attachments={}, version=1, status="draft")
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        row = db.get(CinematicProduction, (plan.id, plan.revision))
    return row


def _video_clip(video_id, db, user):
    video = db.get(VideoGeneration, video_id)
    if video is None or video.user_id != user.id or video.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Scene video not found")
    if video.status != "completed":
        raise HTTPException(status_code=409, detail="Scene video must be completed before linking or assembly")
    url = validate_source_media_url(video.result_url, allowed_exts=VIDEO_EXTS, require_exists=True)
    return STORAGE_DIR / url.removeprefix("/storage/")


@router.get("/plans/{plan_id}/production")
def get_production(plan_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = _owned_plan(plan_id, db, user)
    return _production_out(plan, db.get(CinematicProduction, (plan.id, plan.revision)))


@router.put("/plans/{plan_id}/shots/{shot_id}")
def attach_shot(plan_id: str, shot_id: str, payload: AttachShotIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = _owned_plan(plan_id, db, user)
    if plan.revision != payload.revision:
        raise HTTPException(status_code=409, detail="Plan changed. Reload before linking clips.")
    if shot_id not in {shot["id"] for shot in plan.plan["shots"]}:
        raise HTTPException(status_code=404, detail="Plan shot not found")
    _video_clip(payload.video_id, db, user)
    row = _current_production(plan, db)
    if row.status == "assembling":
        raise HTTPException(status_code=409, detail="Assembly is in progress; wait before changing clips")
    if row.attachments.get(shot_id) == payload.video_id:
        return _production_out(plan, row)
    result = db.execute(update(CinematicProduction).where(
        CinematicProduction.plan_id == plan.id, CinematicProduction.revision == payload.revision,
        CinematicProduction.version == row.version, CinematicProduction.status != "assembling",
    ).values(attachments={**row.attachments, shot_id: payload.video_id}, version=row.version + 1,
             status="draft", result_url=None, error=None))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Production changed. Reload before linking clips.")
    db.commit()
    return _production_out(plan, row)


@router.post("/plans/{plan_id}/assemble")
def assemble_plan(plan_id: str, payload: AssembleIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    plan = _owned_plan(plan_id, db, user)
    if plan.revision != payload.revision:
        raise HTTPException(status_code=409, detail="Plan changed. Reload before assembly.")
    row = _current_production(plan, db)
    if row.status == "completed":
        try:
            validate_source_media_url(row.result_url, allowed_exts=VIDEO_EXTS, require_exists=True)
        except HTTPException:
            row.status = "failed"
            row.error = "Assembled output is missing. Explicitly retry assembly to recreate it."
            row.result_url = None
            db.commit()
            return _production_out(plan, row)
        return _production_out(plan, row)
    if row.status == "assembling":
        return _production_out(plan, row)
    if row.status == "failed" and not payload.retry:
        return _production_out(plan, row)
    ids = [row.attachments.get(shot["id"]) for shot in plan.plan["shots"]]
    if not all(ids):
        raise HTTPException(status_code=409, detail="Link a completed video to every shot before assembly")
    clips = [_video_clip(video_id, db, user) for video_id in ids]
    result = db.execute(update(CinematicProduction).where(
        CinematicProduction.plan_id == plan.id, CinematicProduction.revision == payload.revision,
        CinematicProduction.version == row.version, CinematicProduction.status.in_(["draft", "failed"]),
    ).values(status="assembling", error=None))
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Production changed. Reload assembly status.")
    db.commit()
    destination = STORAGE_DIR / "videos" / f"cinematic-{plan.id}-r{payload.revision}-{uuid.uuid4().hex}.mp4"
    try:
        assemble_clips(clips, destination)
        db.expire_all()
        plan = _owned_plan(plan_id, db, user)
        row = db.get(CinematicProduction, (plan_id, payload.revision))
        if plan.revision != payload.revision:
            row.status = "failed"
            row.error = "Plan changed during assembly; output is not current. Reload and review the updated plan."
        else:
            row.status = "completed"
            row.result_url = "/storage/videos/" + destination.name
    except Exception as exc:
        row = db.get(CinematicProduction, (plan_id, payload.revision))
        row.status = "failed"
        row.error = str(exc)[:500] if isinstance(exc, ValueError) else "Assembly failed. Check local FFmpeg and clip files, then explicitly retry."
    db.commit()
    db.expire_all()
    plan = _owned_plan(plan_id, db, user)
    return _production_out(plan, db.get(CinematicProduction, (plan_id, plan.revision)))
