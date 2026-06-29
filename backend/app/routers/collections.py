from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import (
    AssetCollection,
    CampaignBundle,
    CopyGeneration,
    ProductAsset,
    ProductSceneGeneration,
    Project,
    User,
    VideoGeneration,
)
from ..schemas import (
    AssetCollectionCreate,
    AssetCollectionOut,
    AssetCollectionUpdate,
    CollectionCampaignCreate,
    CollectionCampaignResult,
)
from ..services.brand import with_brand_context
from ..services.briefs import load_project_brief, with_brief_context
from ..services.campaign_builder import _TEMPLATES
from ..services.copy_jobs import enqueue_copy
from ..services.product_scene_jobs import enqueue_product_scene
from ..services.video_jobs import enqueue_video

router = APIRouter(prefix="/api/projects", tags=["asset-collections"])

_READY_ASSET_STATUSES = {"uploaded", "completed"}


def _require_project(db: Session, user: User, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_collection(
    db: Session, user: User, project: Project, collection_id: str
) -> AssetCollection:
    collection = db.get(AssetCollection, collection_id)
    if (
        collection is None
        or collection.user_id != user.id
        or collection.project_id != project.id
    ):
        raise HTTPException(status_code=404, detail="Asset collection not found")
    return collection


def _validate_assets(db: Session, user: User, project: Project, asset_ids: list[str]):
    assets = []
    for asset_id in asset_ids:
        asset = db.get(ProductAsset, asset_id)
        if (
            asset is None
            or asset.user_id != user.id
            or asset.project_id != project.id
            or asset.status not in _READY_ASSET_STATUSES
        ):
            raise HTTPException(status_code=404, detail=f"Product asset not found: {asset_id}")
        assets.append(asset)
    return assets


@router.get("/{project_id}/collections", response_model=list[AssetCollectionOut])
def list_collections(
    project_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    return db.scalars(
        select(AssetCollection)
        .where(AssetCollection.project_id == project.id)
        .order_by(AssetCollection.updated_at.desc())
    ).all()


@router.post("/{project_id}/collections", response_model=AssetCollectionOut, status_code=201)
def create_collection(
    project_id: str,
    payload: AssetCollectionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    _validate_assets(db, user, project, payload.asset_ids)
    collection = AssetCollection(
        user_id=user.id,
        project_id=project.id,
        name=payload.name,
        description=payload.description,
        asset_ids=payload.asset_ids,
        status=payload.status,
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


@router.get("/{project_id}/collections/{collection_id}", response_model=AssetCollectionOut)
def get_collection(
    project_id: str,
    collection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    return _require_collection(db, user, project, collection_id)


@router.put("/{project_id}/collections/{collection_id}", response_model=AssetCollectionOut)
def update_collection(
    project_id: str,
    collection_id: str,
    payload: AssetCollectionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    collection = _require_collection(db, user, project, collection_id)
    changes = payload.model_dump(exclude_unset=True)
    if "asset_ids" in changes and changes["asset_ids"] is not None:
        _validate_assets(db, user, project, changes["asset_ids"])
    for field, value in changes.items():
        setattr(collection, field, value)
    collection.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(collection)
    return collection


@router.delete("/{project_id}/collections/{collection_id}", status_code=204)
def delete_collection(
    project_id: str,
    collection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    collection = _require_collection(db, user, project, collection_id)
    db.delete(collection)
    db.commit()


@router.post(
    "/{project_id}/collections/{collection_id}/campaign",
    response_model=CollectionCampaignResult,
    status_code=201,
)
def create_collection_campaign(
    project_id: str,
    collection_id: str,
    payload: CollectionCampaignCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, project_id)
    collection = _require_collection(db, user, project, collection_id)
    if payload.collection_id != collection.id:
        raise HTTPException(status_code=400, detail="collection_id mismatch")
    brief = load_project_brief(db, project.id, payload.brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="Creative brief not found")
    assets = _validate_assets(db, user, project, collection.asset_ids)
    if not assets:
        raise HTTPException(status_code=400, detail="Collection has no assets")
    template = _TEMPLATES.get(payload.campaign_type)
    if template is None:
        raise HTTPException(status_code=400, detail=f"Unknown campaign type '{payload.campaign_type}'")

    def styled(text: str, asset: ProductAsset) -> str:
        subject = f"{brief.title} / {asset.filename}"
        return with_brief_context(
            with_brand_context(text.format(subject=subject), project), brief
        )

    scene_ids: list[str] = []
    copy_ids: list[str] = []
    video_ids: list[str] = []
    for asset in assets:
        source_image_url = asset.processed_url or asset.original_url
        for preset, mode, base_prompt in template["scenes"]:
            scene = ProductSceneGeneration(
                user_id=user.id,
                project_id=project.id,
                asset_id=asset.id,
                prompt=styled(base_prompt, asset),
                preset=preset,
                mode=mode,
                status="queued",
            )
            db.add(scene)
            db.flush()
            scene_ids.append(scene.id)
        for copy_type, tone in template["copies"]:
            copy = CopyGeneration(
                user_id=user.id,
                project_id=project.id,
                product_asset_id=asset.id,
                copy_type=copy_type,
                tone=tone,
                audience=None,
                prompt=styled("{subject}", asset),
                status="queued",
            )
            db.add(copy)
            db.flush()
            copy_ids.append(copy.id)
        for concept in template["videos"]:
            video = VideoGeneration(
                user_id=user.id,
                project_id=project.id,
                product_scene_id=None,
                source_image_url=source_image_url,
                mode="image_to_video",
                prompt=styled(concept, asset),
                motion_preset="slow_zoom",
                duration_seconds=5,
                status="queued",
            )
            db.add(video)
            db.flush()
            video_ids.append(video.id)

    bundle = CampaignBundle(
        user_id=user.id,
        project_id=project.id,
        brief_id=brief.id,
        selected_asset_id=None,
        title=f"{collection.name} - {payload.campaign_type.replace('_', ' ')}",
        campaign_type=payload.campaign_type,
        status="generated",
        scene_ids=scene_ids,
        copy_ids=copy_ids,
        video_ids=video_ids,
    )
    db.add(bundle)
    db.commit()
    for scene_id in scene_ids:
        enqueue_product_scene(scene_id)
    for copy_id in copy_ids:
        enqueue_copy(copy_id)
    for video_id in video_ids:
        enqueue_video(video_id)
    db.refresh(bundle)
    return CollectionCampaignResult(
        bundle_id=bundle.id,
        title=bundle.title,
        status=bundle.status,
        asset_count=len(assets),
        scene_count=len(scene_ids),
        copy_count=len(copy_ids),
        video_prompt_count=len(video_ids),
        bundle=bundle,
    )
