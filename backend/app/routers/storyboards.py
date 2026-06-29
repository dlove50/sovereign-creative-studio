from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import ProductSceneGeneration, Project, Shot, Storyboard, User, VideoGeneration
from ..schemas import (
    ShotCreate,
    ShotOut,
    ShotUpdate,
    StoryboardCreate,
    StoryboardOut,
    StoryboardUpdate,
)

router = APIRouter(tags=["storyboards"])


def _require_project(db: Session, user: User, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_storyboard(db: Session, user: User, storyboard_id: str) -> Storyboard:
    board = db.get(Storyboard, storyboard_id)
    if board is None or board.user_id != user.id:
        raise HTTPException(status_code=404, detail="Storyboard not found")
    return board


def _require_project_storyboard(
    db: Session, user: User, project: Project, storyboard_id: str
) -> Storyboard:
    board = _require_storyboard(db, user, storyboard_id)
    if board.project_id != project.id:
        raise HTTPException(status_code=404, detail="Storyboard not found")
    return board


def _require_shot(db: Session, board: Storyboard, shot_id: str) -> Shot:
    shot = db.get(Shot, shot_id)
    if shot is None or shot.storyboard_id != board.id:
        raise HTTPException(status_code=404, detail="Shot not found")
    return shot


def _validate_scene_link(
    db: Session, user: User, board: Storyboard, scene_id: str | None
) -> None:
    if scene_id is None:
        return
    scene = db.get(ProductSceneGeneration, scene_id)
    if (
        scene is None
        or scene.user_id != user.id
        or scene.project_id != board.project_id
    ):
        raise HTTPException(status_code=404, detail="Product scene not found")


def _validate_video_link(
    db: Session, user: User, board: Storyboard, video_id: str | None
) -> None:
    if video_id is None:
        return
    video = db.get(VideoGeneration, video_id)
    if (
        video is None
        or video.user_id != user.id
        or video.project_id != board.project_id
    ):
        raise HTTPException(status_code=404, detail="Video not found")


# --- storyboards (project-scoped) --------------------------------------------
@router.get("/api/projects/{project_id}/storyboards", response_model=list[StoryboardOut])
def list_storyboards(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    stmt = (
        select(Storyboard)
        .where(Storyboard.project_id == project.id)
        .order_by(Storyboard.updated_at.desc())
    )
    return db.scalars(stmt).all()


@router.post(
    "/api/projects/{project_id}/storyboards",
    response_model=StoryboardOut,
    status_code=201,
)
def create_storyboard(
    project_id: str,
    payload: StoryboardCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    board = Storyboard(
        user_id=user.id,
        project_id=project.id,
        title=payload.title,
        description=payload.description,
        status=payload.status or "draft",
    )
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


@router.get(
    "/api/projects/{project_id}/storyboards/{storyboard_id}",
    response_model=StoryboardOut,
)
def get_storyboard(
    project_id: str,
    storyboard_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    return _require_project_storyboard(db, user, project, storyboard_id)


@router.put(
    "/api/projects/{project_id}/storyboards/{storyboard_id}",
    response_model=StoryboardOut,
)
def update_storyboard(
    project_id: str,
    storyboard_id: str,
    payload: StoryboardUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    board = _require_project_storyboard(db, user, project, storyboard_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(board, field, value)
    board.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(board)
    return board


@router.delete(
    "/api/projects/{project_id}/storyboards/{storyboard_id}", status_code=204
)
def delete_storyboard(
    project_id: str,
    storyboard_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    board = _require_project_storyboard(db, user, project, storyboard_id)
    for shot in db.scalars(select(Shot).where(Shot.storyboard_id == board.id)).all():
        db.delete(shot)
    db.delete(board)
    db.commit()


@router.get("/api/projects/{project_id}/storyboards/{storyboard_id}/export")
def export_storyboard(
    project_id: str,
    storyboard_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    board = _require_project_storyboard(db, user, project, storyboard_id)
    shots = db.scalars(
        select(Shot).where(Shot.storyboard_id == board.id).order_by(Shot.shot_number)
    ).all()
    lines = [
        board.title,
        f"Project: {project.name}",
        f"Status: {board.status}",
        "",
        board.description or "No storyboard description.",
        "",
        "Shot list:",
    ]
    if not shots:
        lines.append("- No shots planned yet.")
    for shot in shots:
        lines.extend(
            [
                f"{shot.shot_number}. {shot.description or 'Untitled shot'}",
                f"   Duration: {shot.duration_seconds}s",
                f"   Camera: {shot.camera_notes or 'No camera notes'}",
                f"   Prompt: {shot.generation_prompt or 'No generation prompt'}",
                f"   Keyframe scene: {shot.product_scene_id or 'None'}",
                f"   Video: {shot.video_id or 'None'}",
            ]
        )
    filename = f"{board.title.lower().replace(' ', '-')[:48] or 'storyboard'}.txt"
    return Response(
        "\n".join(lines),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- shots (storyboard-scoped) -----------------------------------------------
@router.get("/api/storyboards/{storyboard_id}/shots", response_model=list[ShotOut])
def list_shots(
    storyboard_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    board = _require_storyboard(db, user, storyboard_id)
    stmt = (
        select(Shot)
        .where(Shot.storyboard_id == board.id)
        .order_by(Shot.shot_number)
    )
    return db.scalars(stmt).all()


@router.post(
    "/api/storyboards/{storyboard_id}/shots", response_model=ShotOut, status_code=201
)
def create_shot(
    storyboard_id: str,
    payload: ShotCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    board = _require_storyboard(db, user, storyboard_id)
    _validate_scene_link(db, user, board, payload.product_scene_id)
    _validate_video_link(db, user, board, payload.video_id)
    shot = Shot(
        user_id=user.id,
        storyboard_id=board.id,
        shot_number=payload.shot_number,
        duration_seconds=payload.duration_seconds,
        description=payload.description,
        camera_notes=payload.camera_notes,
        generation_prompt=payload.generation_prompt,
        product_scene_id=payload.product_scene_id,
        video_id=payload.video_id,
    )
    db.add(shot)
    db.commit()
    db.refresh(shot)
    return shot


@router.put(
    "/api/storyboards/{storyboard_id}/shots/{shot_id}", response_model=ShotOut
)
def update_shot(
    storyboard_id: str,
    shot_id: str,
    payload: ShotUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    board = _require_storyboard(db, user, storyboard_id)
    shot = _require_shot(db, board, shot_id)
    changes = payload.model_dump(exclude_unset=True)
    if "product_scene_id" in changes:
        _validate_scene_link(db, user, board, changes["product_scene_id"])
    if "video_id" in changes:
        _validate_video_link(db, user, board, changes["video_id"])
    for field, value in changes.items():
        setattr(shot, field, value)
    shot.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(shot)
    return shot


@router.delete(
    "/api/storyboards/{storyboard_id}/shots/{shot_id}", status_code=204
)
def delete_shot(
    storyboard_id: str,
    shot_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    board = _require_storyboard(db, user, storyboard_id)
    shot = _require_shot(db, board, shot_id)
    db.delete(shot)
    db.commit()
