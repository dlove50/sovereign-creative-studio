import json
import uuid
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import (
    ProductSceneGeneration,
    ProductionProject,
    Project,
    Shot,
    Storyboard,
    User,
    VideoGeneration,
)
from ..schemas import (
    ProductionCreate,
    ProductionOut,
    ProductionUpdate,
    ProductionWorkspaceOut,
)
from ..services.exports import EXPORT_DIR, storage_path_for

router = APIRouter(prefix="/api/projects", tags=["productions"])


def _require_project(db: Session, user: User, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_production(
    db: Session, user: User, project: Project, production_id: str
) -> ProductionProject:
    production = db.get(ProductionProject, production_id)
    if (
        production is None
        or production.user_id != user.id
        or production.project_id != project.id
    ):
        raise HTTPException(status_code=404, detail="Production not found")
    return production


def _validate_storyboards(
    db: Session, user: User, project: Project, storyboard_ids: list[str]
) -> list[Storyboard]:
    storyboards = []
    for storyboard_id in storyboard_ids:
        storyboard = db.get(Storyboard, storyboard_id)
        if (
            storyboard is None
            or storyboard.user_id != user.id
            or storyboard.project_id != project.id
        ):
            raise HTTPException(status_code=404, detail=f"Storyboard not found: {storyboard_id}")
        storyboards.append(storyboard)
    return storyboards


def _validate_shots(
    db: Session, user: User, project: Project, shot_ids: list[str]
) -> list[Shot]:
    shots = []
    for shot_id in shot_ids:
        shot = db.get(Shot, shot_id)
        storyboard = db.get(Storyboard, shot.storyboard_id) if shot else None
        if (
            shot is None
            or shot.user_id != user.id
            or storyboard is None
            or storyboard.project_id != project.id
        ):
            raise HTTPException(status_code=404, detail=f"Shot not found: {shot_id}")
        shots.append(shot)
    return shots


def _validate_videos(
    db: Session, user: User, project: Project, video_ids: list[str]
) -> list[VideoGeneration]:
    videos = []
    for video_id in video_ids:
        video = db.get(VideoGeneration, video_id)
        if video is None or video.user_id != user.id or video.project_id != project.id:
            raise HTTPException(status_code=404, detail=f"Video not found: {video_id}")
        videos.append(video)
    return videos


def _linked_video_ids(shots: list[Shot]) -> list[str]:
    return [shot.video_id for shot in shots if shot.video_id]


def _linked_scene_ids(shots: list[Shot]) -> list[str]:
    return [shot.product_scene_id for shot in shots if shot.product_scene_id]


def _workspace_payload(
    db: Session, user: User, project: Project, production: ProductionProject
) -> ProductionWorkspaceOut:
    storyboards = _validate_storyboards(db, user, project, production.storyboard_ids)
    shots = _validate_shots(db, user, project, production.shot_ids)
    merged_video_ids = list(dict.fromkeys([*production.video_ids, *_linked_video_ids(shots)]))
    videos = _validate_videos(db, user, project, merged_video_ids)
    return ProductionWorkspaceOut(
        production=production,
        storyboards=storyboards,
        shots=shots,
        videos=videos,
        counts={
            "storyboards": len(storyboards),
            "shots": len(shots),
            "videos": len(videos),
            "completed_videos": len([video for video in videos if video.status == "completed"]),
            "exports": len(production.export_urls),
        },
    )


@router.get("/{project_id}/productions", response_model=list[ProductionOut])
def list_productions(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    return db.scalars(
        select(ProductionProject)
        .where(ProductionProject.project_id == project.id)
        .order_by(ProductionProject.updated_at.desc())
    ).all()


@router.post("/{project_id}/productions", response_model=ProductionOut, status_code=201)
def create_production(
    project_id: str,
    payload: ProductionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    _validate_storyboards(db, user, project, payload.storyboard_ids)
    shots = _validate_shots(db, user, project, payload.shot_ids)
    video_ids = list(dict.fromkeys([*payload.video_ids, *_linked_video_ids(shots)]))
    _validate_videos(db, user, project, video_ids)
    production = ProductionProject(
        user_id=user.id,
        project_id=project.id,
        title=payload.title,
        description=payload.description,
        status=payload.status,
        storyboard_ids=payload.storyboard_ids,
        shot_ids=payload.shot_ids,
        video_ids=video_ids,
        export_urls=[],
    )
    db.add(production)
    db.commit()
    db.refresh(production)
    return production


@router.get("/{project_id}/productions/{production_id}", response_model=ProductionWorkspaceOut)
def get_production(
    project_id: str,
    production_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    production = _require_production(db, user, project, production_id)
    return _workspace_payload(db, user, project, production)


@router.put("/{project_id}/productions/{production_id}", response_model=ProductionOut)
def update_production(
    project_id: str,
    production_id: str,
    payload: ProductionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    production = _require_production(db, user, project, production_id)
    changes = payload.model_dump(exclude_unset=True)
    if "storyboard_ids" in changes and changes["storyboard_ids"] is not None:
        _validate_storyboards(db, user, project, changes["storyboard_ids"])
    if "shot_ids" in changes and changes["shot_ids"] is not None:
        shots = _validate_shots(db, user, project, changes["shot_ids"])
        if "video_ids" not in changes or changes["video_ids"] is None:
            changes["video_ids"] = production.video_ids
        changes["video_ids"] = list(
            dict.fromkeys([*changes["video_ids"], *_linked_video_ids(shots)])
        )
    if "video_ids" in changes and changes["video_ids"] is not None:
        _validate_videos(db, user, project, changes["video_ids"])
    for field, value in changes.items():
        setattr(production, field, value)
    production.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(production)
    return production


@router.delete("/{project_id}/productions/{production_id}", status_code=204)
def delete_production(
    project_id: str,
    production_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    production = _require_production(db, user, project, production_id)
    db.delete(production)
    db.commit()


@router.post("/{project_id}/productions/{production_id}/export")
def export_production(
    project_id: str,
    production_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    production = _require_production(db, user, project, production_id)
    workspace = _workspace_payload(db, user, project, production)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"production-{uuid.uuid4().hex}.zip"
    zip_path = EXPORT_DIR / filename
    metadata = {
        "exported_at": datetime.now(timezone.utc),
        "project": {"id": project.id, "name": project.name},
        "production": workspace.production.model_dump(),
        "counts": workspace.counts,
    }
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(metadata, indent=2, default=str))
        zf.writestr(
            "storyboards.json",
            json.dumps([item.model_dump() for item in workspace.storyboards], indent=2, default=str),
        )
        zf.writestr(
            "shots.json",
            json.dumps([item.model_dump() for item in workspace.shots], indent=2, default=str),
        )
        zf.writestr(
            "videos.json",
            json.dumps([item.model_dump() for item in workspace.videos], indent=2, default=str),
        )
        zf.writestr("sequence.txt", _sequence_text(workspace))
        scene_ids = _linked_scene_ids(workspace.shots)
        scenes = []
        for scene_id in scene_ids:
            scene = db.get(ProductSceneGeneration, scene_id)
            if scene and scene.user_id == user.id and scene.project_id == project.id:
                scenes.append(scene)
        zf.writestr(
            "keyframes.json",
            json.dumps(
                [
                    {
                        "id": scene.id,
                        "prompt": scene.prompt,
                        "status": scene.status,
                        "result_url": scene.result_url,
                    }
                    for scene in scenes
                ],
                indent=2,
                default=str,
            ),
        )
        for index, scene in enumerate(scenes, start=1):
            path = storage_path_for(scene.result_url)
            if path and path.is_file():
                zf.write(path, f"keyframes/{index:02d}-{scene.id}{path.suffix}")
        for index, video in enumerate(workspace.videos, start=1):
            path = storage_path_for(video.result_url)
            if path and path.is_file():
                zf.write(path, f"videos/{index:02d}-{video.id}{path.suffix}")
    production.export_urls = [*production.export_urls, f"/storage/exports/{filename}"]
    production.status = "exported"
    production.updated_at = datetime.now(timezone.utc)
    db.commit()
    return FileResponse(
        zip_path, media_type="application/zip", filename="production-package.zip"
    )


def _sequence_text(workspace: ProductionWorkspaceOut) -> str:
    lines = [workspace.production.title, "", "Storyboards:"]
    for storyboard in workspace.storyboards:
        lines.append(f"- {storyboard.title} [{storyboard.status}]")
    lines.append("")
    lines.append("Shot list:")
    for shot in workspace.shots:
        lines.append(
            f"{shot.shot_number}. {shot.description or 'Untitled shot'} "
            f"({shot.duration_seconds}s) - {shot.generation_prompt or 'No prompt'}"
        )
    lines.append("")
    lines.append("Video sequence:")
    for index, video in enumerate(workspace.videos, start=1):
        lines.append(f"{index}. {video.mode} [{video.status}] - {video.prompt}")
    return "\n".join(lines)
