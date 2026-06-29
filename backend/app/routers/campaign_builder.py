from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import CampaignBuilderCreate, CampaignBuilderResult
from ..services.campaign_builder import build_campaign

router = APIRouter(prefix="/api/projects", tags=["campaign-builder"])


@router.post(
    "/{project_id}/campaign-builder",
    response_model=CampaignBuilderResult,
    status_code=201,
)
def create_campaign(
    project_id: str,
    payload: CampaignBuilderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bundle = build_campaign(
        db,
        user,
        project_id,
        brief_id=payload.brief_id,
        asset_id=payload.asset_id,
        campaign_type=payload.campaign_type,
    )
    return CampaignBuilderResult(
        bundle_id=bundle.id,
        title=bundle.title,
        status=bundle.status,
        scene_count=len(bundle.scene_ids),
        copy_count=len(bundle.copy_ids),
        video_prompt_count=len(bundle.video_ids),
        bundle=bundle,
    )
