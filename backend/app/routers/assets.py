import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import STORAGE_DIR
from ..database import get_db
from ..deps import get_current_user
from ..models import ProductAsset, ProductSceneGeneration, Project, User
from ..schemas import ProductAssetOut
from ..services.asset_jobs import enqueue_background_removal

router = APIRouter(prefix="/api/assets", tags=["assets"])

_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_READY_ASSET_FILTERS = {
    "product_scenes": {"uploaded", "completed"},
}


@router.get("", response_model=list[ProductAssetOut])
def list_assets(
    project_id: str | None = None,
    ready_for: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(ProductAsset).where(ProductAsset.user_id == user.id)
    if project_id:
        stmt = stmt.where(ProductAsset.project_id == project_id)
    if ready_for:
        statuses = _READY_ASSET_FILTERS.get(ready_for)
        if statuses is None:
            raise HTTPException(status_code=400, detail="Unknown ready_for filter")
        stmt = stmt.where(ProductAsset.status.in_(statuses))
    stmt = stmt.order_by(ProductAsset.created_at.desc())
    return db.scalars(stmt).all()


@router.get("/{asset_id}", response_model=ProductAssetOut)
def get_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = db.get(ProductAsset, asset_id)
    if asset is None or asset.user_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.post("/from-scene/{scene_id}", response_model=ProductAssetOut, status_code=201)
def asset_from_scene(
    scene_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Save a completed product-scene/attribute-edit result as a reusable
    product asset (so it can be edited again or used in the library)."""
    scene = db.get(ProductSceneGeneration, scene_id)
    if scene is None or scene.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scene not found")
    if scene.status != "completed" or not scene.result_url:
        raise HTTPException(status_code=400, detail="Scene has no completed result")
    asset = ProductAsset(
        user_id=user.id,
        project_id=scene.project_id,
        filename=f"edit-{scene.id[:8]}.png",
        original_url=scene.result_url,
        processed_url=scene.result_url,
        status="completed",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/upload", response_model=ProductAssetOut, status_code=201)
def upload_asset(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    original_name = Path(file.filename or "upload").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Upload must be an image file")

    asset = ProductAsset(
        user_id=user.id,
        project_id=project.id,
        filename=original_name,
        original_url="",
        status="uploaded",
    )
    db.add(asset)
    db.flush()

    stored_name = f"{asset.id}{suffix}"
    upload_dir = STORAGE_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / stored_name
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    asset.filename = stored_name
    asset.original_url = f"/storage/uploads/{stored_name}"
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/{asset_id}/mask", response_model=ProductAssetOut)
def upload_mask(
    asset_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Attach a product mask (white = product) to an asset for inpaint mode."""
    asset = db.get(ProductAsset, asset_id)
    if asset is None or asset.user_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")

    suffix = Path(file.filename or "mask").suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Mask must be an image file")

    stored_name = f"{asset.id}{suffix}"
    mask_dir = STORAGE_DIR / "masks"
    mask_dir.mkdir(parents=True, exist_ok=True)
    destination = mask_dir / stored_name
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    asset.mask_url = f"/storage/masks/{stored_name}"
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/{asset_id}/remove-background", response_model=ProductAssetOut)
def remove_background(
    asset_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asset = db.get(ProductAsset, asset_id)
    if asset is None or asset.user_id != user.id:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.status == "completed":
        return asset
    if asset.status != "processing":
        asset.status = "processing"
        asset.error = None
        db.commit()
        db.refresh(asset)
        enqueue_background_removal(asset.id)
    return asset
