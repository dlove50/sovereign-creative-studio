import mimetypes
import uuid
import json
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import (
    CopyGeneration,
    CampaignBundle,
    CreativeBrief,
    ProductAsset,
    ProductSceneGeneration,
    Project,
    User,
    VideoGeneration,
)
from ..schemas import CampaignBundleCreate, ExportStudioBundleCreate
from ..services.brand import project_brand_kit
from ..services.exports import EXPORT_DIR, build_campaign_zip, storage_path_for

router = APIRouter(prefix="/api/exports", tags=["exports"])

_SOCIAL_PLATFORMS = ["instagram", "facebook", "linkedin", "x"]


def _require_scene(db: Session, user: User, scene_id: str) -> ProductSceneGeneration:
    scene = db.get(ProductSceneGeneration, scene_id)
    if scene is None or scene.user_id != user.id:
        raise HTTPException(status_code=404, detail="Product scene not found")
    if scene.status != "completed":
        raise HTTPException(status_code=409, detail="Product scene is not completed yet")
    return scene


def _require_copy(db: Session, user: User, copy_id: str) -> CopyGeneration:
    copy = db.get(CopyGeneration, copy_id)
    if copy is None or copy.user_id != user.id:
        raise HTTPException(status_code=404, detail="Copy not found")
    if copy.status != "completed" or not copy.result_text:
        raise HTTPException(status_code=409, detail="Copy is not completed yet")
    return copy


def _require_project(db: Session, user: User, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _project_payload(db: Session, project: Project, payload: ExportStudioBundleCreate):
    scenes = [
        scene
        for scene in db.query(ProductSceneGeneration)
        .filter(
            ProductSceneGeneration.project_id == project.id,
            ProductSceneGeneration.status == "completed",
        )
        .order_by(ProductSceneGeneration.created_at.desc())
        .all()
    ]
    copies = [
        copy
        for copy in db.query(CopyGeneration)
        .filter(CopyGeneration.project_id == project.id, CopyGeneration.status == "completed")
        .order_by(CopyGeneration.created_at.desc())
        .all()
    ]
    videos = [
        video
        for video in db.query(VideoGeneration)
        .filter(VideoGeneration.project_id == project.id, VideoGeneration.status == "completed")
        .order_by(VideoGeneration.created_at.desc())
        .all()
    ]
    brief = db.get(CreativeBrief, payload.brief_id) if payload.brief_id else None
    if brief is not None and brief.project_id != project.id:
        raise HTTPException(status_code=404, detail="Creative brief not found")
    bundle = db.get(CampaignBundle, payload.campaign_bundle_id) if payload.campaign_bundle_id else None
    if bundle is not None and bundle.project_id != project.id:
        raise HTTPException(status_code=404, detail="Campaign bundle not found")
    return scenes, copies, videos, brief, bundle


def _write_project_zip(
    *,
    bundle_name: str,
    bundle_kind: str,
    project: Project,
    platforms: list[str],
    scenes: list[ProductSceneGeneration],
    copies: list[CopyGeneration],
    videos: list[VideoGeneration],
    brief: CreativeBrief | None,
    campaign_bundle: CampaignBundle | None,
) -> str:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = EXPORT_DIR / f"{bundle_name}.zip"
    metadata = {
        "exported_at": datetime.now(timezone.utc),
        "bundle_kind": bundle_kind,
        "project": {"id": project.id, "name": project.name},
        "platforms": platforms,
        "brand_kit": project_brand_kit(project).model_dump(),
        "brief": (
            {
                "id": brief.id,
                "title": brief.title,
                "campaign_goal": brief.campaign_goal,
                "target_channels": brief.target_channels,
                "deliverables": brief.deliverables,
                "key_messages": brief.key_messages,
                "creative_direction": brief.creative_direction,
                "reference_notes": brief.reference_notes,
                "status": brief.status,
            }
            if brief
            else None
        ),
        "campaign_bundle": (
            {
                "id": campaign_bundle.id,
                "title": campaign_bundle.title,
                "campaign_type": campaign_bundle.campaign_type,
                "scene_ids": campaign_bundle.scene_ids,
                "copy_ids": campaign_bundle.copy_ids,
                "video_ids": campaign_bundle.video_ids,
            }
            if campaign_bundle
            else None
        ),
        "scene_ids": [scene.id for scene in scenes],
        "copy_ids": [copy.id for copy in copies],
        "video_ids": [video.id for video in videos],
    }
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(metadata, indent=2, default=str))
        if brief:
            zf.writestr("brief.txt", _brief_text(brief))
        zf.writestr(
            "brand-kit.json",
            json.dumps(project_brand_kit(project).model_dump(), indent=2),
        )
        for index, scene in enumerate(scenes, start=1):
            path = storage_path_for(scene.result_url)
            if path and path.is_file():
                zf.write(path, f"images/scene-{index}-{scene.id}{path.suffix}")
            zf.writestr(f"prompts/scene-{index}-{scene.id}.txt", scene.prompt)
        for index, copy in enumerate(copies, start=1):
            if copy.result_text:
                zf.writestr(f"copy/copy-{index}-{copy.id}.txt", copy.result_text)
        for index, video in enumerate(videos, start=1):
            path = storage_path_for(video.result_url)
            if path and path.is_file():
                zf.write(path, f"videos/video-{index}-{video.id}{path.suffix}")
            zf.writestr(f"video-prompts/video-{index}-{video.id}.txt", video.prompt)
        for platform in platforms:
            zf.writestr(
                f"social/{platform}/metadata.json",
                json.dumps(
                    {
                        "platform": platform,
                        "recommended_copy_files": [
                            f"copy/copy-{index}-{copy.id}.txt"
                            for index, copy in enumerate(copies, start=1)
                        ],
                        "recommended_image_count": len(scenes),
                        "recommended_video_count": len(videos),
                    },
                    indent=2,
                ),
            )
    return str(zip_path)


def _brief_text(brief: CreativeBrief) -> str:
    lines = [
        brief.title,
        "",
        f"Goal: {brief.campaign_goal or ''}",
        f"Channels: {brief.target_channels or ''}",
        f"Deliverables: {brief.deliverables or ''}",
        f"Key messages: {brief.key_messages or ''}",
        f"Creative direction: {brief.creative_direction or ''}",
        f"Reference notes: {brief.reference_notes or ''}",
        f"Status: {brief.status}",
    ]
    return "\n".join(lines)


@router.get("/scene/{scene_id}")
def export_scene(
    scene_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scene = _require_scene(db, user, scene_id)
    path = storage_path_for(scene.result_url)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Scene image file not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path, media_type=media_type, filename=f"scene-{scene_id}{path.suffix}"
    )


@router.get("/video/{video_id}")
def export_video(
    video_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    video = db.get(VideoGeneration, video_id)
    if video is None or video.user_id != user.id:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status != "completed":
        raise HTTPException(status_code=409, detail="Video is not completed yet")
    path = storage_path_for(video.result_url)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path, media_type=media_type, filename=f"video-{video_id}{path.suffix}"
    )


@router.get("/copy/{copy_id}")
def export_copy(
    copy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    copy = _require_copy(db, user, copy_id)
    return Response(
        content=copy.result_text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="copy-{copy_id}.txt"'},
    )


@router.post("/campaign-bundle")
def export_campaign_bundle(
    payload: CampaignBundleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not payload.scene_id and not payload.copy_id:
        raise HTTPException(
            status_code=400, detail="Provide scene_id and/or copy_id to export"
        )

    scene = _require_scene(db, user, payload.scene_id) if payload.scene_id else None
    copy = _require_copy(db, user, payload.copy_id) if payload.copy_id else None

    if scene and copy and scene.project_id != copy.project_id:
        raise HTTPException(
            status_code=400, detail="Scene and copy belong to different projects"
        )

    image_path = None
    image_arcname = None
    if scene is not None:
        image_path = storage_path_for(scene.result_url)
        if image_path is None or not image_path.is_file():
            raise HTTPException(status_code=404, detail="Scene image file not found")
        image_arcname = f"scene{image_path.suffix or '.png'}"

    project_id = (scene or copy).project_id
    project = db.get(Project, project_id)

    asset_id = scene.asset_id if scene else copy.product_asset_id
    asset = db.get(ProductAsset, asset_id) if asset_id else None

    metadata = {
        "exported_at": datetime.now(timezone.utc),
        "project": {
            "id": project.id if project else project_id,
            "name": project.name if project else None,
        },
        "asset": (
            {"id": asset.id, "filename": asset.filename} if asset else None
        ),
        "scene": (
            {
                "id": scene.id,
                "preset": scene.preset,
                "mode": scene.mode,
                "prompt": scene.prompt,
                "status": scene.status,
                "created_at": scene.created_at,
                "completed_at": scene.completed_at,
            }
            if scene
            else None
        ),
        "copy": (
            {
                "id": copy.id,
                "copy_type": copy.copy_type,
                "tone": copy.tone,
                "status": copy.status,
                "created_at": copy.created_at,
                "completed_at": copy.completed_at,
            }
            if copy
            else None
        ),
    }

    bundle_name = f"campaign-{uuid.uuid4().hex}"
    zip_path = build_campaign_zip(
        bundle_name=bundle_name,
        image_path=image_path,
        image_arcname=image_arcname,
        copy_text=copy.result_text if copy else None,
        metadata=metadata,
    )
    return FileResponse(
        zip_path, media_type="application/zip", filename="campaign-bundle.zip"
    )


@router.post("/social-bundle")
def export_social_bundle(
    payload: ExportStudioBundleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, payload.project_id)
    platforms = payload.platforms or _SOCIAL_PLATFORMS
    scenes, copies, videos, brief, bundle = _project_payload(db, project, payload)
    zip_path = _write_project_zip(
        bundle_name=f"social-bundle-{uuid.uuid4().hex}",
        bundle_kind="social",
        project=project,
        platforms=platforms,
        scenes=scenes,
        copies=copies,
        videos=videos,
        brief=brief,
        campaign_bundle=bundle,
    )
    return FileResponse(zip_path, media_type="application/zip", filename="social-bundle.zip")


@router.post("/marketing-bundle")
def export_marketing_bundle(
    payload: ExportStudioBundleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = _require_project(db, user, payload.project_id)
    scenes, copies, videos, brief, bundle = _project_payload(db, project, payload)
    zip_path = _write_project_zip(
        bundle_name=f"marketing-bundle-{uuid.uuid4().hex}",
        bundle_kind="marketing",
        project=project,
        platforms=payload.platforms,
        scenes=scenes,
        copies=copies,
        videos=videos,
        brief=brief,
        campaign_bundle=bundle,
    )
    return FileResponse(
        zip_path, media_type="application/zip", filename="marketing-bundle.zip"
    )
