"""Database models: users, projects, credit transactions, generations.

Auth is intentionally not implemented yet (no payments/login this pass) — a
single seeded demo user owns everything. The foreign keys are already in place
so multi-user auth drops in cleanly later."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # Login username (unique) + password hash for real accounts. Nullable so
    # pre-existing/seeded users (accessed via the local owner fallback) are valid.
    username: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(24), default="family_user")
    status: Mapped[str] = mapped_column(String(16), default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    brand_voice: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_colors: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_positioning: Mapped[str | None] = mapped_column(Text, nullable=True)
    campaign_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CreativeBrief(Base):
    """Lightweight campaign plan inside a project. Ownership is derived from the
    parent project (no separate user_id), consistent with the brand kit."""

    __tablename__ = "creative_briefs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    campaign_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_channels: Mapped[str | None] = mapped_column(Text, nullable=True)
    deliverables: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_messages: Mapped[str | None] = mapped_column(Text, nullable=True)
    creative_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    prompt: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(16), default="image")
    provider: Mapped[str] = mapped_column(String(32), default="local_comfyui")
    provider_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits_cost: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProductAsset(Base):
    __tablename__ = "product_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    original_url: Mapped[str] = mapped_column(String(512))
    processed_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mask_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="uploaded")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProductSceneGeneration(Base):
    __tablename__ = "product_scene_generations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("product_assets.id"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    preset: Mapped[str] = mapped_column(String(32))
    # Requested generation mode; null means "use the configured default".
    mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # For attribute_edit auto-seg: the text target (e.g. "pants", "hair") that
    # GroundingDINO+SAM segments into a mask. Null = manual/user-supplied mask.
    target_attribute: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    result_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CopyGeneration(Base):
    __tablename__ = "copy_generations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    product_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_assets.id"), nullable=True, index=True
    )
    product_scene_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_scene_generations.id"), nullable=True, index=True
    )
    copy_type: Mapped[str] = mapped_column(String(32))
    tone: Mapped[str] = mapped_column(String(32))
    audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CampaignBundle(Base):
    """A one-click campaign: orchestrates several scene/copy/video jobs and
    records their ids. Ownership derives from the parent project."""

    __tablename__ = "campaign_bundles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    brief_id: Mapped[str | None] = mapped_column(
        ForeignKey("creative_briefs.id"), nullable=True
    )
    selected_asset_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_assets.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    campaign_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="generated")
    scene_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    copy_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    video_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class AssetCollection(Base):
    """A named group of product assets for multi-asset campaign planning."""

    __tablename__ = "asset_collections"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class VideoGeneration(Base):
    __tablename__ = "video_generations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    product_scene_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_scene_generations.id"), nullable=True, index=True
    )
    source_image_url: Mapped[str] = mapped_column(String(512))
    # Video Studio mode (Phase C11): image_to_video | text_to_video |
    # video_to_video | video_extension | video_upscale.
    mode: Mapped[str] = mapped_column(String(24), default="image_to_video")
    provider: Mapped[str] = mapped_column(String(32), default="local_ltx")
    provider_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    motion_preset: Mapped[str] = mapped_column(String(32))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    quality_preset: Mapped[str | None] = mapped_column(String(40), nullable=True)
    credits_cost: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    result_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    source_video_url: Mapped[str] = mapped_column(String(512))
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="local_whisper")
    model_name: Mapped[str] = mapped_column(String(80), default="base")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits_cost: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AvatarAsset(Base):
    """A reusable avatar source (a photo or short video the user owns)."""

    __tablename__ = "avatar_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    avatar_type: Mapped[str] = mapped_column(String(24), default="photo_avatar")
    source_asset_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    provider: Mapped[str] = mapped_column(String(24), default="local")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Looks made from an avatar share its group_id (the base avatar's id); a base
    # avatar has group_id None. look_label is the short caption shown on the look.
    group_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    look_label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Movie(Base):
    """A scene-by-scene avatar video. Scenes live in scenes_json as a list of
    {id, avatar_id, tts_voice_id, script, status, voice_id, avatar_job_id, error}."""

    __tablename__ = "movies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="Untitled video")
    orientation: Mapped[str] = mapped_column(String(16), default="portrait")
    scenes_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | rendering | completed | failed
    output_video_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class InteractiveVideo(Base):
    """A branching video: nodes live in nodes_json as a list of
    {id, title, video_url, choices: [{label, next}]}; start_node_id is where playback begins."""

    __tablename__ = "interactive_videos"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="Untitled interactive video")
    nodes_json: Mapped[str] = mapped_column(Text, default="[]")
    start_node_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class VoiceAsset(Base):
    """A voice profile: a built-in preset, a local-TTS voice, or an uploaded sample."""

    __tablename__ = "voice_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    voice_type: Mapped[str] = mapped_column(String(24), default="preset")
    provider: Mapped[str] = mapped_column(String(24), default="placeholder")
    sample_file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AvatarJob(Base):
    """A talking-avatar generation job (greeting / photo-to-avatar / video-to-avatar)."""

    __tablename__ = "avatar_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    avatar_id: Mapped[str | None] = mapped_column(
        ForeignKey("avatar_assets.id"), nullable=True, index=True
    )
    voice_id: Mapped[str | None] = mapped_column(
        ForeignKey("voice_assets.id"), nullable=True, index=True
    )
    job_type: Mapped[str] = mapped_column(String(24), default="avatar_greeting")
    script_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    provider: Mapped[str] = mapped_column(String(24), default="placeholder")
    avatar_preset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    avatar_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avatar_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avatar_frames: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avatar_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avatar_cfg: Mapped[float | None] = mapped_column(Float, nullable=True)
    avatar_runtime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_video_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    credits_cost: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Storyboard(Base):
    """A planned video sequence (Phase C11). Shots belong to it."""

    __tablename__ = "storyboards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Shot(Base):
    """A single planned shot inside a storyboard (Phase C11)."""

    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    storyboard_id: Mapped[str] = mapped_column(
        ForeignKey("storyboards.id"), index=True
    )
    shot_number: Mapped[int] = mapped_column(Integer, default=1)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=5)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_scene_id: Mapped[str | None] = mapped_column(
        ForeignKey("product_scene_generations.id"), nullable=True, index=True
    )
    video_id: Mapped[str | None] = mapped_column(
        ForeignKey("video_generations.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ProductionProject(Base):
    """A lightweight production pipeline that assembles planned and generated
    video pieces without introducing a full editor."""

    __tablename__ = "production_projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="planning")
    storyboard_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    shot_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    video_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    export_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class CreditTransaction(Base):
    """Append-only ledger. Negative amount = spend, positive = grant."""

    __tablename__ = "credit_transactions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(120))
    transaction_type: Mapped[str] = mapped_column(String(32), default="generation_charge")
    related_feature: Mapped[str] = mapped_column(String(40), default="base_generation")
    related_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="completed")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    balance_after: Mapped[int] = mapped_column(Integer)
    generation_id: Mapped[str | None] = mapped_column(
        ForeignKey("generations.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class SandboxTopup(Base):
    """Local fake/test credit top-up session. NOT real payment processing —
    no cards, no external providers. Completing one grants credits via the
    existing credit ledger (transaction_type=sandbox_topup)."""

    __tablename__ = "sandbox_topups"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    package_id: Mapped[str] = mapped_column(String(32))
    package_name: Mapped[str] = mapped_column(String(80))
    credits: Mapped[int] = mapped_column(Integer)
    amount_cents: Mapped[int] = mapped_column(Integer)  # fake amount, minor units
    currency: Mapped[str] = mapped_column(String(8), default="CAD")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ledger entry created on completion (also guards double-completion).
    credit_transaction_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
