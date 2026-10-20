from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AvatarJob,
    AvatarAsset,
    CampaignBundle,
    CopyGeneration,
    Generation,
    ProductAsset,
    ProductSceneGeneration,
    Project,
    TranscriptionJob,
    User,
    VideoGeneration,
    VoiceAsset,
)
from ..schemas import LibraryItemOut


def build_library_items(
    db: Session, user: User, project_id: str | None = None
) -> list[LibraryItemOut]:
    project_stmt = select(Project).where(Project.user_id == user.id)
    if project_id:
        project_stmt = project_stmt.where(Project.id == project_id)
    project_names = {
        project.id: project.name for project in db.scalars(project_stmt).all()
    }
    if project_id and project_id not in project_names:
        return []

    items: list[LibraryItemOut] = []

    generation_stmt = select(Generation).where(
        Generation.user_id == user.id,
        Generation.deleted_at.is_(None),
        Generation.media_type == "image",
    )
    if project_id:
        generation_stmt = generation_stmt.where(Generation.project_id == project_id)
    for gen in db.scalars(generation_stmt).all():
        items.append(
            LibraryItemOut(
                id=f"image:{gen.id}",
                type="image",
                project_id=gen.project_id,
                project_name=project_names.get(gen.project_id) if gen.project_id else None,
                title=(
                    "OpenAI image"
                    if gen.provider == "openai_image_api"
                    else "Generated image"
                ),
                prompt=gen.prompt,
                description=gen.error,
                status=gen.status,
                thumbnail_url=gen.file_url,
                asset_url=gen.file_url,
                download_url=gen.file_url if gen.status == "completed" and gen.file_url else None,
                created_at=gen.created_at,
                source_entity_id=gen.id,
                source_entity_type="generation",
            )
        )

    asset_stmt = select(ProductAsset).where(
        ProductAsset.user_id == user.id, ProductAsset.deleted_at.is_(None)
    )
    if project_id:
        asset_stmt = asset_stmt.where(ProductAsset.project_id == project_id)
    for asset in db.scalars(asset_stmt).all():
        project_name = project_names.get(asset.project_id)
        items.append(
            LibraryItemOut(
                id=f"upload:{asset.id}",
                type="upload",
                project_id=asset.project_id,
                project_name=project_name,
                title=asset.filename,
                description="Uploaded product image",
                status=asset.status,
                thumbnail_url=asset.original_url,
                asset_url=asset.original_url,
                download_url=asset.original_url,
                created_at=asset.created_at,
                source_entity_id=asset.id,
                source_entity_type="product_asset",
            )
        )
        if asset.processed_url:
            items.append(
                LibraryItemOut(
                    id=f"processed_asset:{asset.id}",
                    type="processed_asset",
                    project_id=asset.project_id,
                    project_name=project_name,
                    title=f"Processed {asset.filename}",
                    description="Background-removed product asset",
                    status="completed" if asset.status == "completed" else asset.status,
                    thumbnail_url=asset.processed_url,
                    asset_url=asset.processed_url,
                    download_url=asset.processed_url,
                    created_at=asset.updated_at or asset.created_at,
                    source_entity_id=asset.id,
                    source_entity_type="product_asset",
                )
            )

    scene_stmt = select(ProductSceneGeneration).where(
        ProductSceneGeneration.user_id == user.id,
        ProductSceneGeneration.deleted_at.is_(None),
    )
    if project_id:
        scene_stmt = scene_stmt.where(ProductSceneGeneration.project_id == project_id)
    for scene in db.scalars(scene_stmt).all():
        items.append(
            LibraryItemOut(
                id=f"scene:{scene.id}",
                type="scene",
                project_id=scene.project_id,
                project_name=project_names.get(scene.project_id),
                title=f"{scene.preset.title()} product scene",
                prompt=scene.prompt,
                description=scene.error,
                status=scene.status,
                thumbnail_url=scene.result_url,
                asset_url=scene.result_url,
                download_url=f"/api/exports/scene/{scene.id}"
                if scene.status == "completed" and scene.result_url
                else None,
                created_at=scene.created_at,
                source_entity_id=scene.id,
                source_entity_type="product_scene",
            )
        )

    copy_stmt = select(CopyGeneration).where(CopyGeneration.user_id == user.id)
    if project_id:
        copy_stmt = copy_stmt.where(CopyGeneration.project_id == project_id)
    for copy in db.scalars(copy_stmt).all():
        items.append(
            LibraryItemOut(
                id=f"copy:{copy.id}",
                type="copy",
                project_id=copy.project_id,
                project_name=project_names.get(copy.project_id),
                title=copy.copy_type.replace("_", " ").title(),
                prompt=copy.prompt,
                description=copy.result_text or copy.error,
                status=copy.status,
                download_url=f"/api/exports/copy/{copy.id}"
                if copy.status == "completed" and copy.result_text
                else None,
                created_at=copy.created_at,
                source_entity_id=copy.id,
                source_entity_type="copy_generation",
            )
        )

    video_stmt = select(VideoGeneration).where(
        VideoGeneration.user_id == user.id, VideoGeneration.deleted_at.is_(None)
    )
    if project_id:
        video_stmt = video_stmt.where(VideoGeneration.project_id == project_id)
    for video in db.scalars(video_stmt).all():
        items.append(
            LibraryItemOut(
                id=f"video:{video.id}",
                type="video",
                project_id=video.project_id,
                project_name=project_names.get(video.project_id),
                title=video.prompt if video.provider == "imported" else f"{video.motion_preset.replace('_', ' ').title()} video",
                prompt=video.prompt,
                description=video.error,
                status=video.status,
                thumbnail_url=None if video.provider == "imported" else video.source_image_url,
                asset_url=video.result_url,
                download_url=f"/api/exports/video/{video.id}"
                if video.status == "completed" and video.result_url
                else None,
                created_at=video.created_at,
                source_entity_id=video.id,
                source_entity_type="video_generation",
            )
        )

    transcription_stmt = select(TranscriptionJob).where(TranscriptionJob.user_id == user.id)
    if project_id:
        transcription_stmt = transcription_stmt.where(
            TranscriptionJob.project_id == project_id
        )
    for transcript in db.scalars(transcription_stmt).all():
        items.append(
            LibraryItemOut(
                id=f"transcript:{transcript.id}",
                type="transcript",
                project_id=transcript.project_id,
                project_name=project_names.get(transcript.project_id)
                if transcript.project_id
                else None,
                title=transcript.source_filename or "Video transcript",
                prompt=transcript.source_video_url,
                description=transcript.transcript_text
                or transcript.summary_text
                or transcript.error_message,
                status=transcript.status,
                thumbnail_url=None,
                asset_url=None,
                download_url=f"/api/transcriptions/{transcript.id}/download"
                if transcript.status == "completed" and transcript.transcript_text
                else None,
                created_at=transcript.created_at,
                source_entity_id=transcript.id,
                source_entity_type="transcription_job",
            )
        )

    bundle_stmt = select(CampaignBundle).where(CampaignBundle.user_id == user.id)
    if project_id:
        bundle_stmt = bundle_stmt.where(CampaignBundle.project_id == project_id)
    for bundle in db.scalars(bundle_stmt).all():
        counts = (
            f"{len(bundle.scene_ids)} scenes, {len(bundle.copy_ids)} copy, "
            f"{len(bundle.video_ids)} video"
        )
        items.append(
            LibraryItemOut(
                id=f"campaign_bundle:{bundle.id}",
                type="campaign_bundle",
                project_id=bundle.project_id,
                project_name=project_names.get(bundle.project_id),
                title=bundle.title,
                description=f"{bundle.campaign_type.replace('_', ' ').title()} · {counts}",
                status=bundle.status,
                created_at=bundle.created_at,
                source_entity_id=bundle.id,
                source_entity_type="campaign_bundle",
            )
        )

    # Avatar videos appear once a real output exists (Phase 16B onward).
    if not project_id:
        for job in db.scalars(
            select(AvatarJob).where(
                AvatarJob.user_id == user.id,
                AvatarJob.deleted_at.is_(None),
                AvatarJob.output_video_path.is_not(None),
            )
        ).all():
            items.append(
                LibraryItemOut(
                    id=f"avatar_video:{job.id}",
                    type="avatar_video",
                    project_id=None,
                    project_name=None,
                    title="Talking avatar (AI-generated)",
                    description=(
                        f"{job.script_text or ''}"
                        f"{' | ' if job.script_text and job.avatar_preset else ''}"
                        f"{job.avatar_preset or ''}"
                        f"{f' {job.avatar_width}x{job.avatar_height}' if job.avatar_width and job.avatar_height else ''}"
                    ).strip() or None,
                    status=job.status,
                    thumbnail_url=job.output_video_path,
                    asset_url=job.output_video_path,
                    download_url=job.output_video_path,
                    created_at=job.created_at,
                    source_entity_id=job.id,
                    source_entity_type="avatar_job",
                )
            )
        # Owned photo avatars and alternate looks are usable image assets too.
        # They have no project association; keep them out of project-only views.
        for avatar in db.scalars(select(AvatarAsset).where(
            AvatarAsset.user_id == user.id, AvatarAsset.deleted_at.is_(None),
            AvatarAsset.avatar_type == "photo_avatar", AvatarAsset.status == "ready",
            AvatarAsset.source_file_path.is_not(None),
        )).all():
            if not avatar.source_file_path or not avatar.source_file_path.strip():
                continue
            items.append(LibraryItemOut(
                id=f"avatar_image:{avatar.id}", type="image", project_id=None, project_name=None,
                title=avatar.name, description=avatar.look_label or "Avatar image",
                status="completed", thumbnail_url=avatar.thumbnail_path or avatar.source_file_path,
                asset_url=avatar.source_file_path, download_url=avatar.source_file_path,
                created_at=avatar.created_at, source_entity_id=avatar.id, source_entity_type="avatar_asset",
            ))
        # Stored voice samples appear once present (uploaded/generated).
        for voice in db.scalars(
            select(VoiceAsset).where(
                VoiceAsset.user_id == user.id,
                VoiceAsset.deleted_at.is_(None),
                VoiceAsset.sample_file_path.is_not(None),
            )
        ).all():
            items.append(
                LibraryItemOut(
                    id=f"voice:{voice.id}",
                    type="upload",
                    project_id=None,
                    project_name=None,
                    title=f"Voice: {voice.name}",
                    description=voice.voice_type.replace("_", " "),
                    status=voice.status,
                    asset_url=voice.sample_file_path,
                    download_url=voice.sample_file_path,
                    created_at=voice.created_at,
                    source_entity_id=voice.id,
                    source_entity_type="voice_asset",
                )
            )

    from . import music
    for song in music.list_songs():
        if song.get("user_id") != user.id or not song.get("project_id"):
            continue
        if song["project_id"] not in project_names:
            continue
        items.append(LibraryItemOut(
            id=f"music:{song['id']}", type="upload", project_id=song["project_id"],
            project_name=project_names[song["project_id"]], title=song["title"],
            description="Imported music", status="completed", source_entity_id=song["id"],
            source_entity_type="music_song", asset_url=f"/api/music/songs/{song['id']}/audio",
            download_url=f"/api/music/songs/{song['id']}/audio",
            created_at=datetime.fromisoformat(song["created_at"]).replace(tzinfo=None),
        ))
    return sorted(items, key=lambda item: item.created_at, reverse=True)
