from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import CopyGeneration, ProductAsset, ProductSceneGeneration, Project, User
from ..schemas import CopyCreate, CopyOut
from ..services.brand import with_brand_context
from ..services.briefs import load_project_brief, with_brief_context
from ..services.copy_jobs import enqueue_copy

router = APIRouter(prefix="/api/copy", tags=["copy"])


@router.get("", response_model=list[CopyOut])
def list_copy(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(CopyGeneration).where(CopyGeneration.user_id == user.id)
    if project_id:
        stmt = stmt.where(CopyGeneration.project_id == project_id)
    stmt = stmt.order_by(CopyGeneration.created_at.desc())
    return db.scalars(stmt).all()


@router.get("/{copy_id}", response_model=CopyOut)
def get_copy(
    copy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    copy = db.get(CopyGeneration, copy_id)
    if copy is None or copy.user_id != user.id:
        raise HTTPException(status_code=404, detail="Copy not found")
    return copy


@router.post("", response_model=CopyOut, status_code=201)
def create_copy(
    payload: CopyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, payload.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if payload.product_asset_id is not None:
        asset = db.get(ProductAsset, payload.product_asset_id)
        if asset is None or asset.user_id != user.id or asset.project_id != project.id:
            raise HTTPException(status_code=404, detail="Product asset not found")

    if payload.product_scene_id is not None:
        scene = db.get(ProductSceneGeneration, payload.product_scene_id)
        if scene is None or scene.user_id != user.id or scene.project_id != project.id:
            raise HTTPException(status_code=404, detail="Product scene not found")

    brief = None
    if payload.brief_id is not None:
        brief = load_project_brief(db, project.id, payload.brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="Creative brief not found")

    copy = CopyGeneration(
        user_id=user.id,
        project_id=project.id,
        product_asset_id=payload.product_asset_id,
        product_scene_id=payload.product_scene_id,
        copy_type=payload.copy_type,
        tone=payload.tone,
        audience=payload.audience,
        prompt=with_brief_context(
            with_brand_context(payload.prompt, project), brief
        ),
        status="queued",
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    enqueue_copy(copy.id)
    return copy
