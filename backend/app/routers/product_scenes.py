from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import ProductAsset, ProductSceneGeneration, Project, User
from ..schemas import (
    MaskPreviewOut,
    MaskPreviewRequest,
    ProductSceneCreate,
    ProductSceneOut,
)
from ..services.brand import with_brand_context
from ..services.briefs import load_project_brief, with_brief_context
from ..services.mask_preview import build_mask_preview
from ..services.product_scene_jobs import enqueue_product_scene

router = APIRouter(prefix="/api/product-scenes", tags=["product-scenes"])

_SCENE_READY_ASSET_STATUSES = {"uploaded", "completed"}


@router.post("/mask-preview", response_model=MaskPreviewOut)
def mask_preview(
    payload: MaskPreviewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = db.get(ProductAsset, payload.asset_id)
    if asset is None or asset.user_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    image_url = asset.processed_url or asset.original_url
    try:
        return build_mask_preview(image_url, payload.target_attribute)
    except Exception as exc:  # noqa: BLE001 - surface a clean preview error.
        raise HTTPException(status_code=502, detail=f"Mask preview failed: {exc}")


@router.get("", response_model=list[ProductSceneOut])
def list_product_scenes(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(ProductSceneGeneration).where(
        ProductSceneGeneration.user_id == user.id,
        ProductSceneGeneration.deleted_at.is_(None),
    )
    if project_id:
        stmt = stmt.where(ProductSceneGeneration.project_id == project_id)
    stmt = stmt.order_by(ProductSceneGeneration.created_at.desc())
    return db.scalars(stmt).all()


@router.get("/{scene_id}", response_model=ProductSceneOut)
def get_product_scene(
    scene_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scene = db.get(ProductSceneGeneration, scene_id)
    if scene is None or scene.user_id != user.id:
        raise HTTPException(status_code=404, detail="Product scene not found")
    return scene


@router.post("", response_model=ProductSceneOut, status_code=201)
def create_product_scene(
    payload: ProductSceneCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, payload.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    asset = db.get(ProductAsset, payload.asset_id)
    if (
        asset is None
        or asset.user_id != user.id
        or asset.project_id != project.id
        or asset.status not in _SCENE_READY_ASSET_STATUSES
    ):
        raise HTTPException(status_code=404, detail="Product asset not found")

    brief = None
    if payload.brief_id is not None:
        brief = load_project_brief(db, project.id, payload.brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="Creative brief not found")

    prompt = with_brief_context(with_brand_context(payload.prompt, project), brief)
    scene = ProductSceneGeneration(
        user_id=user.id,
        project_id=project.id,
        asset_id=asset.id,
        prompt=prompt,
        preset=payload.preset,
        mode=payload.mode,
        target_attribute=payload.target_attribute,
        status="queued",
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    enqueue_product_scene(scene.id)
    return scene
