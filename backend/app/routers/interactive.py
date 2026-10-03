"""Interactive video API: build and play branching videos from clips already made in the studio."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import ADMIN_ROLE, get_current_user
from ..models import InteractiveVideo, Movie, User, VideoGeneration
from ..services import interactive

router = APIRouter(prefix="/api/interactive", tags=["interactive"])


class ChoiceIn(BaseModel):
    label: str = Field(max_length=interactive.LABEL_LIMIT)
    next: str = Field(max_length=32)


class NodeIn(BaseModel):
    id: str = Field(max_length=32)
    title: str = Field(default="", max_length=120)
    video_url: str = Field(default="", max_length=512)
    choices: list[ChoiceIn] = Field(default_factory=list, max_length=interactive.MAX_CHOICES)


class InteractiveIn(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    nodes: Optional[list[NodeIn]] = Field(default=None, max_length=interactive.MAX_NODES)
    start_node_id: Optional[str] = Field(default=None, max_length=32)


def _out(item: InteractiveVideo) -> dict:
    return {"id": item.id, "title": item.title, "nodes": interactive.load_nodes(item.nodes_json),
            "start_node_id": item.start_node_id, "created_at": item.created_at, "updated_at": item.updated_at}


def _owned(db: Session, user: User, item_id: str) -> InteractiveVideo:
    item = db.get(InteractiveVideo, item_id)
    if item is None or item.deleted_at is not None or (item.user_id != user.id and user.role != ADMIN_ROLE):
        raise HTTPException(status_code=404, detail="Interactive video not found")
    return item


def _apply(item: InteractiveVideo, payload: InteractiveIn) -> None:
    if payload.title is not None:
        item.title = payload.title.strip()[:200] or "Untitled interactive video"
    if payload.nodes is not None:
        try:
            nodes, start = interactive.clean_nodes([n.model_dump() for n in payload.nodes], payload.start_node_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        item.nodes_json = json.dumps(nodes)
        item.start_node_id = start


@router.get("")
def list_interactive(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(
        select(InteractiveVideo)
        .where(InteractiveVideo.user_id == user.id, InteractiveVideo.deleted_at.is_(None))
        .order_by(InteractiveVideo.updated_at.desc())
    ).all()
    return [_out(r) for r in rows]


@router.get("/clips")
def available_clips(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Finished videos the user can drop into a branching video."""
    movies = db.scalars(
        select(Movie)
        .where(Movie.user_id == user.id, Movie.deleted_at.is_(None), Movie.status == "completed",
               Movie.output_video_path.is_not(None))
        .order_by(Movie.updated_at.desc())
    ).all()
    videos = db.scalars(
        select(VideoGeneration)
        .where(VideoGeneration.user_id == user.id, VideoGeneration.deleted_at.is_(None),
               VideoGeneration.status == "completed", VideoGeneration.result_url.is_not(None))
        .order_by(VideoGeneration.created_at.desc()).limit(100)
    ).all()
    clips = [{"title": m.title, "url": m.output_video_path} for m in movies]
    clips += [{"title": (v.prompt or "Video")[:60], "url": v.result_url} for v in videos]
    return [c for c in clips if str(c["url"]).startswith("/storage/")]


@router.post("", status_code=201)
def create_interactive(payload: InteractiveIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = InteractiveVideo(user_id=user.id, title="Untitled interactive video")
    _apply(item, payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _out(item)


@router.get("/{item_id}")
def get_interactive(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_owned(db, user, item_id))


@router.put("/{item_id}")
def update_interactive(item_id: str, payload: InteractiveIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = _owned(db, user, item_id)
    _apply(item, payload)
    db.commit()
    db.refresh(item)
    return _out(item)


@router.delete("/{item_id}", status_code=204)
def delete_interactive(item_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = _owned(db, user, item_id)
    item.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
