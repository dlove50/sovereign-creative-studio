"""Director API: make a finished video from a template and a short brief.

GET    /api/director/templates                 the 12 templates (fields, lengths, shape)
POST   /api/director/projects                  start a video (runs in the background)
GET    /api/director/projects                  your videos, newest first
GET    /api/director/projects/{id}             progress, plan, shots and the finished video
POST   /api/director/projects/{id}/cancel      stop a running video
DELETE /api/director/projects/{id}             remove it (stops it first)
GET    /api/director/series/{id}               a Micro Drama series and its episodes
POST   /api/director/series/{id}/next          start the next episode
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..deps import get_current_user
from ..models import User
from ..services import director, director_templates

router = APIRouter(prefix="/api/director", tags=["director"])


class ProjectIn(BaseModel):
    template: str = Field(min_length=1, max_length=40)
    brief: dict[str, str] = Field(default_factory=dict)
    seconds: int = Field(ge=10, le=180)
    music: bool = True
    narration: bool = True
    voice_id: str | None = Field(default=None, max_length=80)
    planner: str = Field(default="fast", pattern="^(fast|best)$")


class NextEpisodeIn(BaseModel):
    seconds: int | None = Field(default=None, ge=10, le=180)
    direction: str = Field(default="", max_length=400)
    music: bool = True
    planner: str = Field(default="fast", pattern="^(fast|best)$")


def _owned(project_id: str, user: User) -> dict:
    try:
        project = director.get_project(project_id)
    except director.DirectorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if project is None or project["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Video not found.")
    return project


def _public(project: dict) -> dict:
    """Never send the planner prompt back; it only contains the user's own brief but is long."""
    return {k: v for k, v in project.items() if k not in ("prompt", "user_id")}


@router.get("/templates")
def templates(_user: User = Depends(get_current_user)):
    return {
        "credits_per_clip": config.CREDITS_PER_H3_VIDEO,
        "templates": [{k: v for k, v in t.items() if k != "structure"} for t in director_templates.TEMPLATES],
    }


@router.post("/projects", status_code=202)
def start(body: ProjectIn, user: User = Depends(get_current_user)):
    try:
        project = director.create_project(user.id, body.template, body.brief, body.seconds, music=body.music,
                                          narration=body.narration, voice_id=body.voice_id, planner=body.planner)
    except director.DirectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _public(project)


@router.get("/projects")
def projects(user: User = Depends(get_current_user)):
    return [_public(p) for p in director.list_projects(user.id)]


@router.get("/projects/{project_id}")
def project(project_id: str, user: User = Depends(get_current_user)):
    return _public(_owned(project_id, user))


@router.post("/projects/{project_id}/cancel")
def cancel(project_id: str, user: User = Depends(get_current_user)):
    _owned(project_id, user)
    director.cancel(project_id)
    return {"cancelling": True}


@router.delete("/projects/{project_id}", status_code=204)
def delete(project_id: str, user: User = Depends(get_current_user)):
    _owned(project_id, user)
    director.delete_project(project_id)


@router.get("/series/{series_id}")
def series(series_id: str, user: User = Depends(get_current_user)):
    try:
        found = director.get_series(series_id)
    except director.DirectorError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if found is None or found["user_id"] != user.id:
        raise HTTPException(status_code=404, detail="Series not found.")
    return {k: v for k, v in found.items() if k != "user_id"}


@router.post("/series/{series_id}/next", status_code=202)
def next_episode(series_id: str, body: NextEpisodeIn, user: User = Depends(get_current_user)):
    try:
        return _public(director.next_episode(series_id, user.id, body.seconds, body.direction, body.music, body.planner))
    except director.DirectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
