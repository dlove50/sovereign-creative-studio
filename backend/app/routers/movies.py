"""Scene-by-scene movies: drafts, editing, rendering, and delivery polish."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import ADMIN_ROLE, get_current_user
from ..models import AvatarAsset, Movie, User
from ..services import movies, video_agent

router = APIRouter(prefix="/api/movies", tags=["movies"])


class SceneIn(BaseModel):
    id: Optional[str] = Field(default=None, max_length=32)
    avatar_id: Optional[str] = Field(default=None, max_length=32)
    tts_voice_id: Optional[str] = Field(default=None, max_length=200)
    script: str = Field(default="", max_length=1500)


class MovieIn(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    orientation: Optional[Literal["portrait", "landscape"]] = None
    scenes: Optional[list[SceneIn]] = Field(default=None, max_length=movies.MAX_SCENES)


MAX_BATCH_ROWS = 50


class BatchRow(BaseModel):
    title: str = Field(default="", max_length=200)
    script: str = Field(min_length=1, max_length=1500)


class BatchIn(BaseModel):
    avatar_id: str = Field(max_length=32)
    tts_voice_id: Optional[str] = Field(default=None, max_length=200)
    orientation: Literal["portrait", "landscape"] = "portrait"
    rows: list[BatchRow] = Field(min_length=1, max_length=MAX_BATCH_ROWS)
    render: bool = False


class ImproveIn(BaseModel):
    script: str = Field(min_length=3, max_length=1500)


def _out(movie: Movie) -> dict:
    scenes = movies.load_scenes(movie)
    return {
        "id": movie.id, "title": movie.title, "orientation": movie.orientation, "scenes": scenes,
        "status": movie.status, "output_video_path": movie.output_video_path,
        "error_message": movie.error_message, "credits_estimate": movies.cost_estimate(scenes),
        "created_at": movie.created_at, "updated_at": movie.updated_at,
    }


def _owned(db: Session, user: User, movie_id: str) -> Movie:
    movie = db.get(Movie, movie_id)
    if movie is None or movie.deleted_at is not None or (movie.user_id != user.id and user.role != ADMIN_ROLE):
        raise HTTPException(status_code=404, detail="Video not found")
    return movie


@router.get("")
def list_movies(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.scalars(
        select(Movie).where(Movie.user_id == user.id, Movie.deleted_at.is_(None)).order_by(Movie.updated_at.desc())
    ).all()
    return [_out(m) for m in rows]


@router.post("", status_code=201)
def create_movie(payload: MovieIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    movie = Movie(user_id=user.id, title=(payload.title or "Untitled video").strip()[:200] or "Untitled video",
                  orientation=payload.orientation or "portrait")
    movies.save_scenes(movie, [movies.clean_scene(s.model_dump()) for s in (payload.scenes or [SceneIn()])])
    db.add(movie)
    db.commit()
    db.refresh(movie)
    return _out(movie)


@router.get("/{movie_id}")
def get_movie(movie_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_owned(db, user, movie_id))


@router.put("/{movie_id}")
def update_movie(movie_id: str, payload: MovieIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    movie = _owned(db, user, movie_id)
    if movie.status == "rendering":
        raise HTTPException(status_code=409, detail="This video is rendering. Wait for it to finish before editing.")
    if payload.title is not None:
        movie.title = payload.title.strip()[:200] or "Untitled video"
    if payload.orientation is not None:
        movie.orientation = payload.orientation
    if payload.scenes is not None:
        movies.save_scenes(movie, [movies.clean_scene(s.model_dump()) for s in payload.scenes])
        if movie.status != "draft":  # edits after a render make it a draft again
            movie.status, movie.error_message = "draft", None
    db.commit()
    db.refresh(movie)
    return _out(movie)


@router.delete("/{movie_id}", status_code=204)
def delete_movie(movie_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    movie = _owned(db, user, movie_id)
    if movie.status == "rendering":
        raise HTTPException(status_code=409, detail="This video is rendering. Wait for it to finish before deleting.")
    movie.deleted_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/{movie_id}/render")
def render_movie(movie_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    movie = _owned(db, user, movie_id)
    if movie.status == "rendering":
        raise HTTPException(status_code=409, detail="This video is already rendering.")
    scenes = [s for s in movies.load_scenes(movie) if s.get("script", "").strip()]
    if not scenes:
        raise HTTPException(status_code=400, detail="Write a script for at least one scene first.")
    if any(not s.get("avatar_id") for s in scenes):
        raise HTTPException(status_code=400, detail="Pick an avatar look for every scene that has a script.")
    owner = db.get(User, movie.user_id)
    if owner is None or owner.credits < movies.cost_estimate(scenes):
        raise HTTPException(status_code=402, detail=f"Not enough credits: this video needs {movies.cost_estimate(scenes)}.")
    movie.status, movie.error_message, movie.output_video_path = "rendering", None, None
    db.commit()
    movies.enqueue(movie.id)
    db.refresh(movie)
    return _out(movie)


@router.post("/batch", status_code=201)
def create_batch(payload: BatchIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """One single-scene movie per row (HeyGen's Batch Mode). All-or-nothing on credits when rendering."""
    avatar = db.get(AvatarAsset, payload.avatar_id)
    if avatar is None or avatar.deleted_at is not None or avatar.user_id != user.id or not avatar.source_file_path:
        raise HTTPException(status_code=404, detail="Pick one of your avatar looks.")
    per_movie = movies.cost_estimate([{"script": "x"}])
    if payload.render and user.credits < per_movie * len(payload.rows):
        raise HTTPException(
            status_code=402,
            detail=f"Not enough credits: {len(payload.rows)} videos need {per_movie * len(payload.rows)}, you have {user.credits}.",
        )
    created: list[Movie] = []
    for index, row in enumerate(payload.rows, start=1):
        movie = Movie(
            user_id=user.id, orientation=payload.orientation,
            title=(row.title.strip() or f"Batch video {index}")[:200],
            status="rendering" if payload.render else "draft",
        )
        movies.save_scenes(movie, [movies.clean_scene(
            {"avatar_id": avatar.id, "tts_voice_id": payload.tts_voice_id, "script": row.script.strip()})])
        db.add(movie)
        created.append(movie)
    db.commit()
    if payload.render:
        for movie in created:
            movies.enqueue(movie.id)
    return [_out(m) for m in created]


@router.post("/improve-delivery")
def improve_delivery(payload: ImproveIn, user: User = Depends(get_current_user)):
    try:
        return video_agent.improve_delivery(payload.script)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
