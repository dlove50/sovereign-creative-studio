from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import CampaignBundle, CreativeBrief, Project, User
from ..schemas import (
    BrandKitOut,
    BrandKitUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectWorkspaceOut,
)
from ..services.brand import BRAND_FIELDS, project_brand_kit
from ..services.library import build_library_items

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    stmt = (
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = Project(
        user_id=user.id, name=payload.name, description=payload.description
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/brand-kit", response_model=BrandKitOut)
def get_brand_kit(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project_brand_kit(project)


@router.put("/{project_id}/brand-kit", response_model=BrandKitOut)
def update_brand_kit(
    project_id: str,
    payload: BrandKitUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    for field in BRAND_FIELDS:
        value = getattr(payload, field)
        cleaned = value.strip() if isinstance(value, str) else value
        setattr(project, field, cleaned or None)
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project_brand_kit(project)


@router.get("/{project_id}/workspace", response_model=ProjectWorkspaceOut)
def get_project_workspace(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    briefs = db.scalars(
        select(CreativeBrief)
        .where(CreativeBrief.project_id == project.id)
        .order_by(CreativeBrief.updated_at.desc())
    ).all()

    bundles = db.scalars(
        select(CampaignBundle)
        .where(CampaignBundle.project_id == project.id)
        .order_by(CampaignBundle.created_at.desc())
    ).all()

    items = build_library_items(db, user, project.id)
    by_type = {
        "upload": [item for item in items if item.type == "upload"],
        "processed_asset": [
            item for item in items if item.type == "processed_asset"
        ],
        "scene": [item for item in items if item.type == "scene"],
        "copy": [item for item in items if item.type == "copy"],
        "video": [item for item in items if item.type == "video"],
        "campaign": [item for item in items if item.type == "campaign"],
    }
    counts = {key: len(value) for key, value in by_type.items()}
    latest = max(
        [project.updated_at or project.created_at, *[item.created_at for item in items]]
    )

    return ProjectWorkspaceOut(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        brand_kit=project_brand_kit(project),
        creative_briefs=briefs,
        campaign_bundles=bundles,
        uploaded_assets=by_type["upload"],
        processed_assets=by_type["processed_asset"],
        product_scenes=by_type["scene"],
        copy_generations=by_type["copy"],
        video_generations=by_type["video"],
        campaign_items=by_type["campaign"],
        counts_by_type=counts,
        latest_activity_at=latest,
    )
