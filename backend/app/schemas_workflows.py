"""Video, transcription, storyboard, production, library, and status schemas."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .schema_types import *  # noqa: F403 - schema facade intentionally re-exports literals
from .schemas_core import BrandKitOut, CreativeBriefOut

VideoMode = Literal[
    "image_to_video",
    "text_to_video",
    "video_to_video",
    "video_extension",
    "video_upscale",
]

VideoQualityPreset = Literal[
    "safe_preview",
    "standard_local",
    "best_local",
    "image_to_video_best",
]


class VideoCreate(BaseModel):
    project_id: str
    product_scene_id: Optional[str] = None
    source_image_url: Optional[str] = None
    prompt: str = Field(min_length=1, max_length=2000)
    motion_preset: VideoMotionPreset
    duration_seconds: int = Field(default=5, ge=2, le=30)
    mode: VideoMode = "image_to_video"
    provider: Literal["local_ltx", "local_wan", "local_h3", "seedance_api"] = "local_ltx"
    quality_preset: Optional[VideoQualityPreset] = "standard_local"
    # Optional creative brief whose context is appended to the video prompt.
    brief_id: Optional[str] = None


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    product_scene_id: Optional[str] = None
    source_image_url: str
    mode: str
    provider: str = "local_ltx"
    provider_task_id: Optional[str] = None
    prompt: str
    motion_preset: str
    duration_seconds: int
    quality_preset: Optional[str] = None
    status: str
    result_url: Optional[str] = None
    output_url: Optional[str] = None
    file_size_bytes: Optional[int] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    credits_cost: int = 10

    @model_validator(mode="after")
    def _fill_output_url(self) -> "VideoOut":
        if self.output_url is None:
            self.output_url = self.result_url
        return self


class TranscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: Optional[str] = None
    source_video_url: str
    source_filename: Optional[str] = None
    status: str
    transcript_text: Optional[str] = None
    summary_text: Optional[str] = None
    detected_language: Optional[str] = None
    duration_seconds: Optional[float] = None
    provider: str
    model_name: str
    error_message: Optional[str] = None
    credits_cost: int
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class TranscriptionSummaryIn(BaseModel):
    summary_type: Literal[
        "short_summary",
        "bullet_summary",
        "key_points",
        "social_caption_ideas",
        "scene_breakdown",
    ] = "short_summary"


class VideoProviderReadiness(BaseModel):
    available: bool
    cost: int
    note: Optional[str] = None


class VideoModeOption(BaseModel):
    id: str
    name: str
    description: str
    source_required: bool
    available: bool
    backend: str
    note: Optional[str] = None
    providers: dict[str, VideoProviderReadiness] = Field(default_factory=dict)


class ImageProviderReadiness(BaseModel):
    available: bool
    cost: int
    note: Optional[str] = None


class ImageModeOption(BaseModel):
    id: str
    name: str
    description: str
    source_required: bool
    providers: dict[str, ImageProviderReadiness] = Field(default_factory=dict)


class StoryboardCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=3000)
    status: Optional[str] = Field(default="draft", max_length=16)


class StoryboardUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=3000)
    status: Optional[str] = Field(default=None, max_length=16)


class StoryboardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    title: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime


class ShotCreate(BaseModel):
    shot_number: int = Field(default=1, ge=1, le=999)
    duration_seconds: int = Field(default=5, ge=1, le=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    camera_notes: Optional[str] = Field(default=None, max_length=2000)
    generation_prompt: Optional[str] = Field(default=None, max_length=2000)
    product_scene_id: Optional[str] = None
    video_id: Optional[str] = None


class ShotUpdate(BaseModel):
    shot_number: Optional[int] = Field(default=None, ge=1, le=999)
    duration_seconds: Optional[int] = Field(default=None, ge=1, le=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    camera_notes: Optional[str] = Field(default=None, max_length=2000)
    generation_prompt: Optional[str] = Field(default=None, max_length=2000)
    product_scene_id: Optional[str] = None
    video_id: Optional[str] = None


class ShotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    storyboard_id: str
    shot_number: int
    duration_seconds: int
    description: Optional[str] = None
    camera_notes: Optional[str] = None
    generation_prompt: Optional[str] = None
    product_scene_id: Optional[str] = None
    video_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


LibraryItemType = Literal[
    "upload",
    "processed_asset",
    "image",
    "scene",
    "copy",
    "video",
    "transcript",
    "campaign",
    "campaign_bundle",
    "avatar_video",
]


class CampaignBuilderCreate(BaseModel):
    brief_id: str
    asset_id: str
    campaign_type: CampaignType


class CampaignBundleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    brief_id: Optional[str] = None
    selected_asset_id: Optional[str] = None
    title: str
    campaign_type: str
    status: str
    scene_ids: list[str] = Field(default_factory=list)
    copy_ids: list[str] = Field(default_factory=list)
    video_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CampaignBuilderResult(BaseModel):
    bundle_id: str
    title: str
    status: str
    scene_count: int
    copy_count: int
    video_prompt_count: int
    bundle: CampaignBundleOut


class AssetCollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    asset_ids: list[str] = Field(default_factory=list)
    status: str = Field(default="active", max_length=16)


class AssetCollectionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    asset_ids: Optional[list[str]] = None
    status: Optional[str] = Field(default=None, max_length=16)


class AssetCollectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    name: str
    description: Optional[str] = None
    asset_ids: list[str] = Field(default_factory=list)
    status: str
    created_at: datetime
    updated_at: datetime


class CollectionCampaignCreate(BaseModel):
    brief_id: str
    collection_id: str
    campaign_type: CampaignType


class CollectionCampaignResult(BaseModel):
    bundle_id: str
    title: str
    status: str
    asset_count: int
    scene_count: int
    copy_count: int
    video_prompt_count: int
    bundle: CampaignBundleOut


class ProductionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=3000)
    status: str = Field(default="planning", max_length=24)
    storyboard_ids: list[str] = Field(default_factory=list)
    shot_ids: list[str] = Field(default_factory=list)
    video_ids: list[str] = Field(default_factory=list)


class ProductionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=3000)
    status: Optional[str] = Field(default=None, max_length=24)
    storyboard_ids: Optional[list[str]] = None
    shot_ids: Optional[list[str]] = None
    video_ids: Optional[list[str]] = None


class ProductionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    title: str
    description: Optional[str] = None
    status: str
    storyboard_ids: list[str] = Field(default_factory=list)
    shot_ids: list[str] = Field(default_factory=list)
    video_ids: list[str] = Field(default_factory=list)
    export_urls: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProductionWorkspaceOut(BaseModel):
    production: ProductionOut
    storyboards: list[StoryboardOut]
    shots: list[ShotOut]
    videos: list[VideoOut]
    counts: dict[str, int]


class LibraryItemOut(BaseModel):
    id: str
    type: LibraryItemType
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    title: str
    prompt: Optional[str] = None
    description: Optional[str] = None
    status: str
    thumbnail_url: Optional[str] = None
    asset_url: Optional[str] = None
    download_url: Optional[str] = None
    created_at: datetime
    source_entity_id: str
    source_entity_type: str


class ProjectWorkspaceOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    brand_kit: BrandKitOut
    creative_briefs: list[CreativeBriefOut]
    campaign_bundles: list[CampaignBundleOut]
    uploaded_assets: list[LibraryItemOut]
    processed_assets: list[LibraryItemOut]
    product_scenes: list[LibraryItemOut]
    copy_generations: list[LibraryItemOut]
    video_generations: list[LibraryItemOut]
    campaign_items: list[LibraryItemOut]
    counts_by_type: dict[str, int]
    latest_activity_at: datetime


class StatusOut(BaseModel):
    status: str
    generator_backend: str
    product_scene_backend: str
    product_scene_model: str
    product_scene_mode: str
    copy_backend: str
    video_backend: str
    video_engine: str
    transcription_backend: str
    transcription_available: bool = False
    transcription_ffmpeg_available: bool = False
    transcription_faster_whisper_available: bool = False
    transcription_model_name: str = "base"
    transcription_model_dir: str = ""
    transcription_device: str = "cpu"
    transcription_compute_type: str = "int8"
    transcription_message: Optional[str] = None
    comfyui_base_url: str
    comfyui_configured: bool
    comfyui_reachable: bool = False
    comfyui_error: Optional[str] = None
    openai_configured: bool
    storage_path: str
    storage_writable: bool


class ComfyUIStatusOut(BaseModel):
    base_url: str
    reachable: bool
    version: Optional[str] = None
    error: Optional[str] = None


class ModelCheckOut(BaseModel):
    name: str
    category: str
    installed: bool
    active: bool = False
    experimental: bool = False
    backend: str = "ComfyUI"
    source: str = ""
    details: list[str] = Field(default_factory=list)
    required_nodes: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    missing_nodes: list[str] = Field(default_factory=list)
    missing_models: list[str] = Field(default_factory=list)


class WorkflowCheckOut(BaseModel):
    name: str
    kind: str
    path: str
    exists: bool
    active: bool = False
    experimental: bool = False
    details: list[str] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)


class ModelManagerStatusOut(BaseModel):
    status: str
    current_config: dict[str, str]
    video_generation_ready: str
    comfyui: ComfyUIStatusOut
    image_models: list[ModelCheckOut]
    video_models: list[ModelCheckOut]
    copy_models: list[ModelCheckOut]
    support_models: list[ModelCheckOut]
    workflows: list[WorkflowCheckOut]
