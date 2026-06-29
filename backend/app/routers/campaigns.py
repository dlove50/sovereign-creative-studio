from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import CopyGeneration, ProductAsset, ProductSceneGeneration, Project, User
from ..presets import get_preset, render_scene_prompt
from ..schemas import CampaignFromPresetCreate, CampaignOut
from ..services.brand import with_brand_context
from ..services.briefs import load_project_brief, with_brief_context
from ..services.copy_jobs import enqueue_copy
from ..services.product_scene_jobs import enqueue_product_scene

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

_READY_ASSET_STATUSES = {"uploaded", "completed"}
_DEFAULT_PRODUCT_NAME = "your product"


@router.post("/from-preset", response_model=CampaignOut, status_code=201)
def create_campaign_from_preset(
    payload: CampaignFromPresetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    preset = get_preset(payload.preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")

    project = db.get(Project, payload.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    asset = db.get(ProductAsset, payload.asset_id)
    if (
        asset is None
        or asset.user_id != user.id
        or asset.project_id != project.id
        or asset.status not in _READY_ASSET_STATUSES
    ):
        raise HTTPException(status_code=404, detail="Product asset not found")

    brief = None
    if payload.brief_id is not None:
        brief = load_project_brief(db, project.id, payload.brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="Creative brief not found")

    product_name = (payload.product_name or "").strip() or _DEFAULT_PRODUCT_NAME
    scene_prompt = with_brief_context(
        with_brand_context(render_scene_prompt(preset, product_name), project), brief
    )
    copy_prompt = with_brief_context(
        with_brand_context(product_name, project), brief
    )

    # 1. Product-scene job from the preset's scene style.
    scene = ProductSceneGeneration(
        user_id=user.id,
        project_id=project.id,
        asset_id=asset.id,
        prompt=scene_prompt,
        preset=preset.scene_preset,
        mode=preset.scene_mode,
        status="queued",
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)

    # 2. Copy job linked to the same asset and the new scene.
    copy = CopyGeneration(
        user_id=user.id,
        project_id=project.id,
        product_asset_id=asset.id,
        product_scene_id=scene.id,
        copy_type=preset.copy_type,
        tone=preset.tone,
        audience=preset.audience_hint,
        prompt=copy_prompt,
        status="queued",
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)

    enqueue_product_scene(scene.id)
    enqueue_copy(copy.id)

    return CampaignOut(preset_id=preset.id, scene_job=scene, copy_job=copy)
