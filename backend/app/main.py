"""FastAPI application entrypoint."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import FRONTEND_ORIGIN, STORAGE_DIR
from .database import SessionLocal
from .db_migrate import upgrade_to_head
from .models import AvatarJob, Movie, TranscriptionJob, VideoGeneration, CinematicProduction
from .services.private_storage import PublicStorage
from .routers import cloud_media
from .routers import music as music_router
from .routers import music_dub as music_dub_router
from .routers import music_import as music_import_router
from .routers import director as director_router
from .routers import motion_studio as motion_studio_router
from .routers import (
    admin,
    assets,
    audio_merge,
    audio_transcribe,
    auth,
    avatars,
    briefs,
    campaign_builder,
    campaigns,
    collections,
    copy,
    creative_director,
    exports,
    generations,
    library,
    models,
    movies as movies_router,
    openai_media,
    presets,
    product_scenes,
    productions,
    projects,
    status,
    storyboards,
    transcriptions,
    users,
    auto_clips as auto_clips_router,
    captions as captions_router,
    interactive as interactive_router,
    slides as slides_router,
    ocr as ocr_router,
    voice_studio as voice_studio_router,
    prompt_assist as prompt_assist_router,
    translate as translate_router,
    voice_library as voice_library_router,
    speech_cleanup as speech_cleanup_router,
    recordings as recordings_router,
    assistant as assistant_router,
    developers as developers_router,
    video_agent,
    videos,
    workflow_manager as workflow_manager_router,
)
from .seed import ensure_owner_admin
from .services import workflow_manager
from .startup import run_startup_checks

logger = logging.getLogger("sovereign.main")
_INTERRUPTED_MSG = "Job interrupted by server restart."


def _recover_interrupted_jobs(db) -> None:
    """Mark any jobs left in 'running' state as failed.

    Workers are in-process daemon threads; a clean or unclean process exit
    kills them without running their exception handlers, leaving DB records
    stuck in 'running' forever. Recover on the next startup so the UI does
    not show permanently-spinning jobs.
    """
    now = datetime.now(timezone.utc)
    recovered = 0
    # Avatar and movie queues live in memory too, so their queued work is lost on exit.
    stuck = (
        (VideoGeneration, ("running",)),
        (TranscriptionJob, ("running",)),
        (AvatarJob, ("queued", "running")),
        (Movie, ("rendering",)),
        (CinematicProduction, ("assembling",)),
    )
    for model, statuses in stuck:
        rows = db.query(model).filter(model.status.in_(statuses)).all()
        for row in rows:
            row.status = "failed"
            if hasattr(row, "error"):
                row.error = _INTERRUPTED_MSG
            if hasattr(row, "error_message"):
                row.error_message = _INTERRUPTED_MSG
            if hasattr(row, "completed_at") and row.completed_at is None:
                row.completed_at = now
            recovered += 1
    if recovered:
        db.commit()
        logger.warning("[startup] Recovered %d interrupted job(s) left in 'running' state.", recovered)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Surface config problems early as clear warnings.
    run_startup_checks()
    # Bring the database to the latest schema (creates it on a fresh install,
    # upgrades a legacy create_all database without requiring a reset).
    upgrade_to_head()
    # Re-apply any persisted Workflow Manager selections (validated; stale or
    # now-unavailable choices fall back safely).
    workflow_manager.load_persisted_and_apply()
    with SessionLocal() as db:
        ensure_owner_admin(db)
        _recover_interrupted_jobs(db)
    from .services.cloud_media import recover as recover_cloud_jobs
    recover_cloud_jobs()
    from .services.motion_studio import recover as recover_motion_jobs
    recover_motion_jobs()
    yield


app = FastAPI(
    title="Sovereign Creative Studio API", version="0.1.0", lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/storage", PublicStorage(directory=STORAGE_DIR), name="storage")
app.include_router(cloud_media.router)
app.include_router(music_router.router)
app.include_router(music_dub_router.router)
app.include_router(music_import_router.router)
app.include_router(director_router.router)
app.include_router(motion_studio_router.router)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(admin.router)
app.include_router(projects.router)
app.include_router(briefs.router)
app.include_router(campaign_builder.router)
app.include_router(storyboards.router)
app.include_router(generations.router)
app.include_router(library.router)
app.include_router(models.router)
app.include_router(openai_media.router)
app.include_router(assets.router)
app.include_router(avatars.router)
app.include_router(video_agent.router)
app.include_router(movies_router.router)
app.include_router(speech_cleanup_router.router)
app.include_router(recordings_router.router)
app.include_router(assistant_router.router)
app.include_router(developers_router.router)
app.include_router(slides_router.router)
app.include_router(ocr_router.router)
app.include_router(voice_studio_router.router)
app.include_router(prompt_assist_router.router)
app.include_router(interactive_router.router)
app.include_router(captions_router.router)
app.include_router(translate_router.router)
app.include_router(voice_library_router.router)
app.include_router(auto_clips_router.router)
app.include_router(product_scenes.router)
app.include_router(productions.router)
app.include_router(copy.router)
app.include_router(creative_director.router)
app.include_router(videos.router)
app.include_router(audio_merge.router)
app.include_router(audio_transcribe.router)
app.include_router(transcriptions.router)
app.include_router(presets.router)
app.include_router(campaigns.router)
app.include_router(collections.router)
app.include_router(exports.router)
app.include_router(status.router)
app.include_router(workflow_manager_router.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
