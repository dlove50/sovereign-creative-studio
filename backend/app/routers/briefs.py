from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import CreativeBrief, Project, User
from ..schemas import CreativeBriefCreate, CreativeBriefOut, CreativeBriefUpdate

router = APIRouter(prefix="/api/projects", tags=["creative-briefs"])


def _require_project(db: Session, user: User, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_brief(db: Session, project: Project, brief_id: str) -> CreativeBrief:
    brief = db.get(CreativeBrief, brief_id)
    if brief is None or brief.project_id != project.id:
        raise HTTPException(status_code=404, detail="Creative brief not found")
    return brief


@router.get("/{project_id}/briefs", response_model=list[CreativeBriefOut])
def list_briefs(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    stmt = (
        select(CreativeBrief)
        .where(CreativeBrief.project_id == project.id)
        .order_by(CreativeBrief.updated_at.desc())
    )
    return db.scalars(stmt).all()


@router.post("/{project_id}/briefs", response_model=CreativeBriefOut, status_code=201)
def create_brief(
    project_id: str,
    payload: CreativeBriefCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    brief = CreativeBrief(
        project_id=project.id,
        title=payload.title,
        campaign_goal=payload.campaign_goal,
        target_channels=payload.target_channels,
        deliverables=payload.deliverables,
        key_messages=payload.key_messages,
        creative_direction=payload.creative_direction,
        reference_notes=payload.reference_notes,
        selected_asset_ids=payload.selected_asset_ids,
        status=payload.status or "draft",
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)
    return brief


@router.get("/{project_id}/briefs/{brief_id}", response_model=CreativeBriefOut)
def get_brief(
    project_id: str,
    brief_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    return _require_brief(db, project, brief_id)


@router.put("/{project_id}/briefs/{brief_id}", response_model=CreativeBriefOut)
def update_brief(
    project_id: str,
    brief_id: str,
    payload: CreativeBriefUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    brief = _require_brief(db, project, brief_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(brief, field, value)
    brief.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(brief)
    return brief


@router.delete("/{project_id}/briefs/{brief_id}", status_code=204)
def delete_brief(
    project_id: str,
    brief_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    brief = _require_brief(db, project, brief_id)
    db.delete(brief)
    db.commit()
