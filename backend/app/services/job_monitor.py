"""Local admin job monitor.

Read-only aggregation of generation jobs across their tables (base image/video,
product scene, copy, video, transcription, avatar video) into one normalized list
with summary counts. Campaigns, storyboards, shots, and productions use editorial states
(draft/planning/generated), not job states, so they are intentionally not listed
here. Private/family use only.

There is no retry or clear-failed action: jobs run as fire-and-forget background
tasks at creation time (no safe re-enqueue), and failed generation rows are
referenced by the credit ledger (generation_id / related_id), so deleting them
would break the usage/ledger audit trail. The monitor is therefore read-only.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    AvatarJob,
    CopyGeneration,
    Generation,
    ProductSceneGeneration,
    Project,
    TranscriptionJob,
    User,
    VideoGeneration,
)
from ..schemas import AdminJobCountsOut, AdminJobMonitorItemOut, AdminJobMonitorOut


def build_job_monitor(
    db: Session,
    *,
    status: str | None = None,
    feature: str | None = None,
    limit: int = 100,
) -> AdminJobMonitorOut:
    users = {u.id: u.name for u in db.scalars(select(User)).all()}
    projects = {p.id: p.name for p in db.scalars(select(Project)).all()}

    items = (
        _base_items(db, users, projects)
        + _scene_items(db, users, projects)
        + _copy_items(db, users, projects)
        + _video_items(db, users, projects)
        + _transcription_items(db, users, projects)
        + _avatar_items(db, users, projects)
    )

    # Counts are global (over every job), independent of the display filters.
    counts = AdminJobCountsOut(
        queued=sum(1 for i in items if i.status == "queued"),
        running=sum(1 for i in items if i.status == "running"),
        completed=sum(1 for i in items if i.status == "completed"),
        failed=sum(1 for i in items if i.status == "failed"),
        total=len(items),
    )

    if status:
        items = [i for i in items if i.status == status]
    if feature:
        items = [i for i in items if i.feature == feature]
    items.sort(key=lambda i: i.created_at, reverse=True)
    items = items[: min(max(limit, 1), 500)]

    return AdminJobMonitorOut(counts=counts, jobs=items)


def _item(
    *,
    row,
    feature,
    users,
    projects,
    title,
    result_url,
    updated_at,
    provider=None,
    mode=None,
    error=None,
):
    return AdminJobMonitorItemOut(
        id=row.id,
        feature=feature,
        status=row.status,
        user_id=row.user_id,
        user_name=users.get(row.user_id),
        project_id=getattr(row, "project_id", None),
        project_name=projects.get(getattr(row, "project_id", None)) if getattr(row, "project_id", None) else None,
        title=title,
        provider=provider,
        mode=mode,
        result_url=result_url,
        error=error if error is not None else getattr(row, "error", None),
        created_at=row.created_at,
        updated_at=updated_at,
    )


def _base_items(db, users, projects):
    # Dismissed/archived rows (deleted_at set) are hidden from the monitor.
    rows = db.scalars(select(Generation).where(Generation.deleted_at.is_(None))).all()
    items = []
    for r in rows:
        # A base_generation with media_type=video is a legacy /create-page video
        # attempt (the old image-only path). Relabel it so it is not mistaken for
        # a real Video Studio (/videos) job/failure.
        if r.media_type == "video":
            title = f"Legacy Create-page video attempt (use Video Studio /videos): {r.prompt}"
        else:
            title = r.prompt
        items.append(
            _item(
                row=r,
                feature="base_generation",
                users=users,
                projects=projects,
                title=title,
                result_url=r.file_url,
                updated_at=r.updated_at,
                provider=r.provider,
                mode="image_edit" if r.source_image_url else "text_to_image",
            )
        )
    return items


def _scene_items(db, users, projects):
    rows = db.scalars(
        select(ProductSceneGeneration).where(ProductSceneGeneration.deleted_at.is_(None))
    ).all()
    return [
        _item(
            row=r,
            feature="product_scene",
            users=users,
            projects=projects,
            title=r.prompt or f"{r.preset} scene",
            result_url=r.result_url,
            updated_at=r.completed_at or r.updated_at,
        )
        for r in rows
    ]


def _copy_items(db, users, projects):
    rows = db.scalars(select(CopyGeneration)).all()
    return [
        _item(
            row=r,
            feature="copy",
            users=users,
            projects=projects,
            title=r.copy_type,
            result_url=None,
            updated_at=r.completed_at,
        )
        for r in rows
    ]


def _video_items(db, users, projects):
    rows = db.scalars(
        select(VideoGeneration).where(VideoGeneration.deleted_at.is_(None))
    ).all()
    return [
        _item(
            row=r,
            feature="video",
            users=users,
            projects=projects,
            title=r.prompt,
            result_url=r.result_url,
            updated_at=r.completed_at,
            provider=r.provider,
            mode=r.mode,
        )
        for r in rows
    ]


def _transcription_items(db, users, projects):
    rows = db.scalars(select(TranscriptionJob)).all()
    return [
        _item(
            row=r,
            feature="transcription",
            users=users,
            projects=projects,
            title=r.source_filename or r.source_video_url,
            result_url=None,
            updated_at=r.completed_at or r.updated_at,
            provider=r.provider,
            mode="video_to_text",
            error=r.error_message,
        )
        for r in rows
    ]


def _avatar_items(db, users, projects):
    rows = db.scalars(
        select(AvatarJob).where(AvatarJob.deleted_at.is_(None), AvatarJob.job_type == "avatar_talking")
    ).all()
    return [
        _item(
            row=r,
            feature="avatar_video",
            users=users,
            projects=projects,
            title=r.script_text or "Talking avatar",
            result_url=r.output_video_path,
            updated_at=r.completed_at or r.updated_at,
            provider=r.provider,
            mode=r.avatar_preset,
            error=r.error_message,
        )
        for r in rows
    ]
