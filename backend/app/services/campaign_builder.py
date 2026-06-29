"""One-click Campaign Builder.

Orchestrates the *existing* scene, copy, and video generators from a single
request. It only creates the job records (with brand-kit + creative-brief context
applied, exactly like the manual routers) and enqueues them — no generation logic
is duplicated here.

Videos use the selected asset image as their source (product scenes are still
queued/async at build time), so the mock/LTX video worker can run immediately.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import (
    CampaignBundle,
    CopyGeneration,
    ProductAsset,
    ProductSceneGeneration,
    Project,
    User,
    VideoGeneration,
)
from .brand import with_brand_context
from .briefs import load_project_brief, with_brief_context
from .copy_jobs import enqueue_copy
from .product_scene_jobs import enqueue_product_scene
from .video_jobs import enqueue_video

_READY_ASSET_STATUSES = {"uploaded", "completed"}

# Each template lists: scenes (preset, mode, prompt), copies (copy_type, tone),
# and video concept prompts. "{subject}" is filled from the brief title.
_TEMPLATES: dict[str, dict] = {
    "product_launch": {
        "scenes": [
            ("studio", "advertising_scene", "Hero product shot of {subject}"),
            ("luxury", "advertising_scene", "Premium advertising scene featuring {subject}"),
            ("social ad", "img2img", "Social media product scene of {subject}"),
        ],
        "copies": [
            ("product_description", "professional"),
            ("instagram_caption", "playful"),
            ("facebook_ad", "bold"),
        ],
        "videos": [
            "Product launch teaser: slow reveal of {subject} with premium lighting",
        ],
    },
    "ecommerce": {
        "scenes": [
            ("studio", "advertising_scene", "Clean ecommerce hero image of {subject}"),
            ("studio", "img2img", "Clean white-background product image of {subject}"),
        ],
        "copies": [
            ("product_description", "professional"),
            ("seo_title", "professional"),
        ],
        "videos": [],
    },
    "social_media": {
        "scenes": [
            ("social ad", "img2img", "Instagram-ready scene with {subject}"),
            ("social ad", "img2img", "Facebook ad scene with {subject}"),
        ],
        "copies": [
            ("instagram_caption", "playful"),
            ("facebook_ad", "friendly"),
        ],
        "videos": [],
    },
    "fashion_editorial": {
        "scenes": [
            ("luxury", "fashion_editorial", "Editorial fashion scene featuring {subject}"),
            ("luxury", "fashion_editorial", "Luxury storefront editorial scene with {subject}"),
            ("luxury", "fashion_editorial", "Magazine cover style scene with {subject}"),
        ],
        "copies": [
            ("product_description", "luxury"),
        ],
        "videos": [],
    },
    "luxury_brand": {
        "scenes": [
            ("luxury", "advertising_scene", "Premium advertising scene featuring {subject}"),
            ("luxury", "fashion_editorial", "Luxury editorial scene with {subject}"),
        ],
        "copies": [
            ("product_description", "luxury"),
        ],
        "videos": [],
    },
    "custom": {
        "scenes": [
            ("studio", "img2img", "Product scene featuring {subject}"),
        ],
        "copies": [
            ("product_description", "professional"),
        ],
        "videos": [],
    },
}


def build_campaign(
    db: Session, user: User, project_id: str, brief_id: str, asset_id: str, campaign_type: str
) -> CampaignBundle:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    brief = load_project_brief(db, project.id, brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail="Creative brief not found")

    asset = db.get(ProductAsset, asset_id)
    if (
        asset is None
        or asset.user_id != user.id
        or asset.project_id != project.id
        or asset.status not in _READY_ASSET_STATUSES
    ):
        raise HTTPException(status_code=404, detail="Product asset not found")

    template = _TEMPLATES.get(campaign_type)
    if template is None:
        raise HTTPException(status_code=400, detail=f"Unknown campaign type '{campaign_type}'")

    subject = (brief.title or "").strip() or "the product"
    source_image_url = asset.processed_url or asset.original_url

    def styled(text: str) -> str:
        return with_brief_context(with_brand_context(text, project), brief)

    scene_ids: list[str] = []
    for preset, mode, base_prompt in template["scenes"]:
        scene = ProductSceneGeneration(
            user_id=user.id,
            project_id=project.id,
            asset_id=asset.id,
            prompt=styled(base_prompt.format(subject=subject)),
            preset=preset,
            mode=mode,
            status="queued",
        )
        db.add(scene)
        db.flush()
        scene_ids.append(scene.id)

    copy_ids: list[str] = []
    for copy_type, tone in template["copies"]:
        copy = CopyGeneration(
            user_id=user.id,
            project_id=project.id,
            product_asset_id=asset.id,
            copy_type=copy_type,
            tone=tone,
            # Audience comes from the brand kit / brief context woven into the
            # prompt; the brief model has no separate audience field.
            audience=None,
            prompt=styled(subject),
            status="queued",
        )
        db.add(copy)
        db.flush()
        copy_ids.append(copy.id)

    video_ids: list[str] = []
    for concept in template["videos"]:
        video = VideoGeneration(
            user_id=user.id,
            project_id=project.id,
            product_scene_id=None,
            source_image_url=source_image_url,
            prompt=styled(concept.format(subject=subject)),
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
        selected_asset_id=asset.id,
        title=f"{subject} — {campaign_type.replace('_', ' ')}",
        campaign_type=campaign_type,
        status="generated",
        scene_ids=scene_ids,
        copy_ids=copy_ids,
        video_ids=video_ids,
    )
    db.add(bundle)
    db.commit()

    # Enqueue after commit so the worker sessions see persisted rows.
    for scene_id in scene_ids:
        enqueue_product_scene(scene_id)
    for copy_id in copy_ids:
        enqueue_copy(copy_id)
    for video_id in video_ids:
        enqueue_video(video_id)

    db.refresh(bundle)
    return bundle
