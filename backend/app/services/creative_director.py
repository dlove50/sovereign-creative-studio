from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CampaignBundle,
    CopyGeneration,
    CreativeBrief,
    ProductAsset,
    ProductSceneGeneration,
    Project,
    VideoGeneration,
)
from ..schemas import CreativeDirectorOut, CreativeDirectorRecommendation
from .brand import brand_context
from .briefs import brief_context


def build_recommendations(
    db: Session, project: Project, brief: CreativeBrief | None = None
) -> CreativeDirectorOut:
    assets = db.scalars(
        select(ProductAsset).where(ProductAsset.project_id == project.id)
    ).all()
    scenes = db.scalars(
        select(ProductSceneGeneration).where(
            ProductSceneGeneration.project_id == project.id
        )
    ).all()
    copies = db.scalars(
        select(CopyGeneration).where(CopyGeneration.project_id == project.id)
    ).all()
    videos = db.scalars(
        select(VideoGeneration).where(VideoGeneration.project_id == project.id)
    ).all()
    bundles = db.scalars(
        select(CampaignBundle).where(CampaignBundle.project_id == project.id)
    ).all()

    brand = brand_context(project)
    brief_text = brief_context(brief) if brief else None
    completed_scenes = [scene for scene in scenes if scene.status == "completed"]
    completed_copy = [copy for copy in copies if copy.status == "completed"]
    completed_videos = [video for video in videos if video.status == "completed"]

    recommendations = [
        _campaign_recommendation(project, brief, bundles, brand, brief_text),
        _scene_recommendation(assets, completed_scenes, brand, brief_text),
        _copy_recommendation(completed_copy, brand, brief_text),
        _video_recommendation(completed_scenes, completed_videos, brief_text),
        _audience_recommendation(project, brief, brand),
    ]
    summary = (
        f"{project.name} has {len(assets)} assets, {len(completed_scenes)} completed "
        f"scenes, {len(completed_copy)} copy outputs, and {len(completed_videos)} videos."
    )
    return CreativeDirectorOut(
        project_id=project.id,
        brief_id=brief.id if brief else None,
        summary=summary,
        recommendations=recommendations,
    )


def _campaign_recommendation(
    project: Project,
    brief: CreativeBrief | None,
    bundles: list[CampaignBundle],
    brand: str | None,
    brief_text: str | None,
) -> CreativeDirectorRecommendation:
    if bundles:
        recommendation = "Build the next iteration from the strongest existing campaign bundle."
        rationale = "Campaign history exists, so reuse proven structure and refine the creative."
        confidence = 0.82
    elif brief:
        recommendation = f"Launch from the creative brief '{brief.title}' with one coordinated scene, copy, and video prompt."
        rationale = "A brief is available, which gives the campaign a focused goal and deliverables."
        confidence = 0.78
    else:
        recommendation = "Create a short creative brief before generating the next campaign."
        rationale = "A brief will align scenes, copy, and video before production."
        confidence = 0.7
    if brand:
        rationale += " Brand kit guidance is available and should be reused."
    if brief_text:
        rationale += " The selected brief adds channel and message context."
    return CreativeDirectorRecommendation(
        category="campaign",
        recommendation=recommendation,
        rationale=rationale,
        confidence=confidence,
    )


def _scene_recommendation(
    assets: list[ProductAsset],
    scenes: list[ProductSceneGeneration],
    brand: str | None,
    brief_text: str | None,
) -> CreativeDirectorRecommendation:
    if not assets:
        recommendation = "Upload a hero product asset before generating more scenes."
        rationale = "Product photography needs a source asset to preserve the subject."
        confidence = 0.9
    elif not scenes:
        recommendation = "Generate one polished hero scene and one secondary lifestyle scene."
        rationale = "The project has assets but no completed product scenes yet."
        confidence = 0.82
    else:
        recommendation = "Create a variant scene that changes the environment while preserving product identity."
        rationale = "Completed scenes exist; variation will expand campaign coverage."
        confidence = 0.76
    if brand:
        rationale += " Match brand colors and style keywords."
    if brief_text:
        rationale += " Align the scene with the brief's creative direction."
    return CreativeDirectorRecommendation(
        category="scene",
        recommendation=recommendation,
        rationale=rationale,
        confidence=confidence,
    )


def _copy_recommendation(
    copies: list[CopyGeneration],
    brand: str | None,
    brief_text: str | None,
) -> CreativeDirectorRecommendation:
    if not copies:
        recommendation = "Generate a product description and one social caption from the same brief."
        rationale = "No completed copy exists yet, so start with reusable core messaging."
        confidence = 0.82
    else:
        recommendation = "Create channel-specific copy variants from the best completed message."
        rationale = "Existing copy can be adapted for social, ads, and product listings."
        confidence = 0.74
    if brand:
        rationale += " Keep tone consistent with the brand voice."
    if brief_text:
        rationale += " Reuse the brief's key messages."
    return CreativeDirectorRecommendation(
        category="copy",
        recommendation=recommendation,
        rationale=rationale,
        confidence=confidence,
    )


def _video_recommendation(
    scenes: list[ProductSceneGeneration],
    videos: list[VideoGeneration],
    brief_text: str | None,
) -> CreativeDirectorRecommendation:
    if not scenes:
        recommendation = "Plan video after at least one completed product scene is ready."
        rationale = "Image-to-video works best from a strong source scene."
        confidence = 0.8
    elif not videos:
        recommendation = "Generate a short Test/Fast product reveal video from the best scene."
        rationale = "Completed scenes exist, but no video output has been created yet."
        confidence = 0.78
    else:
        recommendation = "Use the shot planner to sequence completed clips into a campaign arc."
        rationale = "Video outputs exist, so the next step is structure and continuity."
        confidence = 0.75
    if brief_text:
        rationale += " The selected brief should guide pacing and motion."
    return CreativeDirectorRecommendation(
        category="video",
        recommendation=recommendation,
        rationale=rationale,
        confidence=confidence,
    )


def _audience_recommendation(
    project: Project, brief: CreativeBrief | None, brand: str | None
) -> CreativeDirectorRecommendation:
    if brief and brief.target_channels:
        recommendation = f"Prioritize messaging for {brief.target_channels}."
        rationale = "The selected brief names target channels, so audience framing can be specific."
        confidence = 0.78
    elif project.target_audience:
        recommendation = f"Shape creative for {project.target_audience}."
        rationale = "The brand kit includes a target audience."
        confidence = 0.76
    else:
        recommendation = "Define a target audience in the Brand Kit or Creative Brief."
        rationale = "Audience guidance will improve copy tone and scene choices."
        confidence = 0.72
    if brand:
        rationale += " Brand positioning should remain consistent across channels."
    return CreativeDirectorRecommendation(
        category="audience",
        recommendation=recommendation,
        rationale=rationale,
        confidence=confidence,
    )
