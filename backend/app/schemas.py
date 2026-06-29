"""Pydantic request/response schemas."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

MediaType = Literal["image", "video"]
ProductScenePreset = Literal["studio", "luxury", "outdoor", "social ad"]
ProductSceneMode = Literal[
    "img2img",
    "ipadapter",
    "inpaint",
    "segmented_composite",
    "segmented_composite_polished",
    "advertising_scene",
    "fashion_editorial",
    "creative_fashion_edit",
    "creative_edit",
    "character_reimagination",
    "fashion_transformation",
    "cinematic_scene_builder",
    "clothing_style_edit",
    "pose_edit",
    "pose_stylized",
    "film_scene",
    "attribute_edit",
]
CopyType = Literal[
    "product_description",
    "instagram_caption",
    "facebook_ad",
    "tiktok_hook",
    "seo_title",
]
CopyTone = Literal["luxury", "friendly", "bold", "professional", "playful"]
VideoMotionPreset = Literal[
    "slow_zoom",
    "orbit",
    "handheld",
    "product_reveal",
    "product_motion",
    "cinematic_push",
    "runway_walk",
    "parallax",
    "dolly_in",
    "subtle_breathing",
]
CampaignType = Literal[
    "product_launch",
    "ecommerce",
    "social_media",
    "fashion_editorial",
    "luxury_brand",
    "custom",
]
FamilyUserRole = Literal["owner_admin", "family_user", "guest"]
FamilyUserStatus = Literal["active", "disabled"]
CreditTransactionType = Literal[
    "generation_charge",
    "refund",
    "manual_add",
    "manual_remove",
    "adjustment",
    "sandbox_topup",
]
CreditTransactionStatus = Literal["completed", "failed", "refunded", "manual"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    username: Optional[str] = None
    name: str
    role: FamilyUserRole = "family_user"
    status: FamilyUserStatus = "active"
    notes: Optional[str] = None
    credits: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FamilyUserCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    role: FamilyUserRole = "family_user"
    status: FamilyUserStatus = "active"
    initial_credits: int = Field(default=0, ge=0, le=100000)
    notes: Optional[str] = Field(default=None, max_length=2000)
    email: Optional[str] = Field(default=None, max_length=255)


class FamilyUserUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    role: Optional[FamilyUserRole] = None
    status: Optional[FamilyUserStatus] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class FamilyUserOut(BaseModel):
    id: str
    display_name: str
    email: str
    role: FamilyUserRole
    status: FamilyUserStatus
    notes: Optional[str] = None
    credit_balance: int
    created_at: datetime
    updated_at: datetime
    last_activity_at: Optional[datetime] = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BrandKitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    brand_name: Optional[str] = None
    brand_voice: Optional[str] = None
    target_audience: Optional[str] = None
    primary_colors: Optional[str] = None
    style_keywords: Optional[str] = None
    negative_keywords: Optional[str] = None
    product_positioning: Optional[str] = None
    campaign_notes: Optional[str] = None


class BrandKitUpdate(BaseModel):
    brand_name: Optional[str] = Field(default=None, max_length=160)
    brand_voice: Optional[str] = Field(default=None, max_length=2000)
    target_audience: Optional[str] = Field(default=None, max_length=2000)
    primary_colors: Optional[str] = Field(default=None, max_length=1000)
    style_keywords: Optional[str] = Field(default=None, max_length=2000)
    negative_keywords: Optional[str] = Field(default=None, max_length=2000)
    product_positioning: Optional[str] = Field(default=None, max_length=3000)
    campaign_notes: Optional[str] = Field(default=None, max_length=3000)


class CreativeBriefCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    campaign_goal: Optional[str] = Field(default=None, max_length=3000)
    target_channels: Optional[str] = Field(default=None, max_length=1000)
    deliverables: Optional[str] = Field(default=None, max_length=2000)
    key_messages: Optional[str] = Field(default=None, max_length=3000)
    creative_direction: Optional[str] = Field(default=None, max_length=3000)
    reference_notes: Optional[str] = Field(default=None, max_length=3000)
    selected_asset_ids: list[str] = Field(default_factory=list)
    status: Optional[str] = Field(default="draft", max_length=16)


class CreativeBriefUpdate(BaseModel):
    """All fields optional; only provided fields are applied (partial update)."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    campaign_goal: Optional[str] = Field(default=None, max_length=3000)
    target_channels: Optional[str] = Field(default=None, max_length=1000)
    deliverables: Optional[str] = Field(default=None, max_length=2000)
    key_messages: Optional[str] = Field(default=None, max_length=3000)
    creative_direction: Optional[str] = Field(default=None, max_length=3000)
    reference_notes: Optional[str] = Field(default=None, max_length=3000)
    selected_asset_ids: Optional[list[str]] = None
    status: Optional[str] = Field(default=None, max_length=16)


class CreativeBriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    title: str
    campaign_goal: Optional[str] = None
    target_channels: Optional[str] = None
    deliverables: Optional[str] = None
    key_messages: Optional[str] = None
    creative_direction: Optional[str] = None
    reference_notes: Optional[str] = None
    selected_asset_ids: list[str] = Field(default_factory=list)
    status: str
    created_at: datetime
    updated_at: datetime


class GenerationCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    media_type: MediaType = "image"
    project_id: Optional[str] = None
    provider: Literal["local_comfyui", "openai_image_api"] = "local_comfyui"
    mode: Literal["text_to_image", "image_edit"] = "text_to_image"
    source_image_url: Optional[str] = None
    # Local image quality preset (model). None -> server default. Ignored for OpenAI.
    quality_preset: Optional[str] = Field(default=None, max_length=40)
    # Prompt style preset (e.g. "animal_portrait"). None/"none" -> no change.
    style_preset: Optional[str] = Field(default=None, max_length=40)
    # Image Quality Mode (e.g. "animal_pet") -> picks model + prompt enhancer.
    image_mode: Optional[str] = Field(default=None, max_length=40)


class ImagePresetOut(BaseModel):
    id: str
    label: str
    description: str
    recommended: bool
    is_default: bool
    ready: bool
    missing: list[str] = []
    detail: str


class StylePresetOut(BaseModel):
    id: str
    label: str
    description: str


class ImageModeOut(BaseModel):
    id: str
    label: str
    description: str
    recommended_model: str
    recommended_ready: bool
    effective_preset: str
    effective_model: str
    setup_note: Optional[str] = None
    subject_size_guidance: Optional[str] = None


class FaceRefineStatusOut(BaseModel):
    available: bool
    enabled: bool
    workflow_present: bool
    detail: str


class ImagePresetsOut(BaseModel):
    quality_presets: list[ImagePresetOut]
    style_presets: list[StylePresetOut]
    image_modes: list[ImageModeOut]
    face_refine: FaceRefineStatusOut


class GenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    prompt: str
    media_type: str
    provider: str = "local_comfyui"
    provider_task_id: Optional[str] = None
    provider_model: Optional[str] = None
    source_image_url: Optional[str] = None
    status: str
    file_url: Optional[str] = None
    error: Optional[str] = None
    credits_cost: int
    project_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProductAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    filename: str
    original_url: str
    processed_url: Optional[str] = None
    mask_url: Optional[str] = None
    status: str
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ProductSceneCreate(BaseModel):
    project_id: str
    asset_id: str
    prompt: str = Field(min_length=1, max_length=2000)
    preset: ProductScenePreset
    # Optional; when omitted the backend uses the configured default mode.
    mode: Optional[ProductSceneMode] = None
    # Optional creative brief whose context is appended to the prompt.
    brief_id: Optional[str] = None
    # For attribute_edit: the text target to auto-segment (e.g. "pants", "hair").
    # When provided, GroundingDINO+SAM generates the mask automatically.
    target_attribute: Optional[str] = Field(default=None, max_length=64)


class MaskPreviewRequest(BaseModel):
    asset_id: str
    target_attribute: str = Field(min_length=1, max_length=64)


class MaskPreviewOut(BaseModel):
    mask_url: Optional[str] = None
    route: str


class ProductSceneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    asset_id: str
    prompt: str
    preset: str
    mode: Optional[str] = None
    target_attribute: Optional[str] = None
    status: str
    result_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class CopyCreate(BaseModel):
    project_id: str
    product_asset_id: Optional[str] = None
    product_scene_id: Optional[str] = None
    copy_type: CopyType
    tone: CopyTone
    audience: Optional[str] = Field(default=None, max_length=255)
    prompt: str = Field(min_length=1, max_length=2000)
    # Optional creative brief whose context is appended to the prompt.
    brief_id: Optional[str] = None


class CopyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    product_asset_id: Optional[str] = None
    product_scene_id: Optional[str] = None
    copy_type: str
    tone: str
    audience: Optional[str] = None
    prompt: str
    result_text: Optional[str] = None
    status: str
    error: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class PresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    scene_preset: str
    scene_mode: str
    scene_prompt_template: str
    copy_type: str
    tone: str
    audience_hint: str


class CampaignFromPresetCreate(BaseModel):
    project_id: str
    asset_id: str
    preset_id: str
    product_name: Optional[str] = Field(default=None, max_length=160)
    # Optional creative brief whose context is appended to scene + copy prompts.
    brief_id: Optional[str] = None


class CampaignOut(BaseModel):
    preset_id: str
    scene_job: ProductSceneOut
    copy_job: CopyOut


class CampaignBundleCreate(BaseModel):
    scene_id: Optional[str] = None
    copy_id: Optional[str] = None


class ExportStudioBundleCreate(BaseModel):
    project_id: str
    brief_id: Optional[str] = None
    campaign_bundle_id: Optional[str] = None
    platforms: list[str] = Field(default_factory=list)


class CreativeDirectorRequest(BaseModel):
    project_id: str
    brief_id: Optional[str] = None


class CreativeDirectorRecommendation(BaseModel):
    category: str
    recommendation: str
    rationale: str
    confidence: float = Field(ge=0, le=1)


class CreativeDirectorOut(BaseModel):
    project_id: str
    brief_id: Optional[str] = None
    summary: str
    recommendations: list[CreativeDirectorRecommendation]


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
    provider: Literal["local_ltx", "seedance_api"] = "local_ltx"
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


# --- Workflow Manager --------------------------------------------------------
class WorkflowOptionOut(BaseModel):
    id: str
    name: str
    available: bool
    active: bool
    experimental: bool = False
    backend: Optional[str] = None
    note: Optional[str] = None


class WorkflowManagerStatusOut(BaseModel):
    active_image_model: str
    active_scene_workflow: str
    active_scene_mode: str
    active_video_backend: str
    active_copy_backend: str
    active_copy_model: str
    generator_backend: str
    product_scene_backend: str
    comfyui_base_url: str
    comfyui_reachable: bool


class WorkflowManagerModelsOut(BaseModel):
    image_models: list[WorkflowOptionOut]
    scene_modes: list[WorkflowOptionOut]
    video_models: list[WorkflowOptionOut]
    copy_models: list[WorkflowOptionOut]


class WorkflowConfigUpdate(BaseModel):
    image_model: Optional[str] = None
    scene_workflow: Optional[str] = None
    scene_mode: Optional[str] = None
    video_backend: Optional[str] = None
    copy_backend: Optional[str] = None


class WorkflowConfigUpdateResult(BaseModel):
    applied: dict[str, str]
    warnings: list[str]
    status: WorkflowManagerStatusOut


class AdminUserSummaryOut(BaseModel):
    id: str
    display_name: str
    email: str
    role: FamilyUserRole
    status: FamilyUserStatus
    notes: Optional[str] = None
    credit_balance: int
    created_at: datetime
    updated_at: datetime
    last_activity_at: Optional[datetime] = None


class AdminJobSummaryOut(BaseModel):
    id: str
    type: str
    label: str
    status: str
    project_id: Optional[str] = None
    prompt: Optional[str] = None
    error: Optional[str] = None
    result_url: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class AdminCreditTransactionOut(BaseModel):
    id: str
    user_id: str
    user_name: str
    transaction_type: CreditTransactionType
    amount: int
    related_feature: str
    related_id: Optional[str] = None
    status: CreditTransactionStatus
    reason: str
    note: Optional[str] = None
    balance_after: int
    generation_id: Optional[str] = None
    created_at: datetime


class AdminCreditAdjustmentIn(BaseModel):
    user_id: str
    amount: int = Field(gt=0, le=100000)
    note: str = Field(min_length=1, max_length=1000)


class AdminCreditRefundIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=1000)


SandboxTopupStatus = Literal["pending", "completed", "cancelled", "failed"]


class TopupPackageOut(BaseModel):
    id: str
    name: str
    credits: int
    amount_cents: int
    currency: str
    price_display: str


class SandboxTopupCreate(BaseModel):
    user_id: str
    package_id: str = Field(min_length=1, max_length=32)
    note: Optional[str] = Field(default=None, max_length=1000)


class SandboxTopupOut(BaseModel):
    id: str
    user_id: str
    user_name: str
    package_id: str
    package_name: str
    credits: int
    amount_cents: int
    amount_display: str
    currency: str
    status: SandboxTopupStatus
    note: Optional[str] = None
    credit_transaction_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class AdminUsageSummaryOut(BaseModel):
    id: str
    user_id: str
    user_name: str
    feature: str
    label: str
    status: str
    credits_charged: int
    ledger_status: str
    related_transaction_id: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class AdminDashboardOut(BaseModel):
    title: str
    mode: str
    service_health: StatusOut
    model_status: ModelManagerStatusOut
    workflow_status: WorkflowManagerStatusOut
    workflow_config: dict[str, str]
    family_users: list[AdminUserSummaryOut]
    recent_jobs: list[AdminJobSummaryOut]
    failed_jobs: list[AdminJobSummaryOut]
    recent_credit_transactions: list[AdminCreditTransactionOut]
    recent_usage: list[AdminUsageSummaryOut]


class AdminSafeResetOut(BaseModel):
    applied: dict[str, str]
    warnings: list[str]
    status: WorkflowManagerStatusOut


class BackupOut(BaseModel):
    id: str
    filename: str
    created_at: datetime
    size_bytes: int
    download_url: str


# --- Job monitor -------------------------------------------------------------
class AdminJobMonitorItemOut(BaseModel):
    id: str
    feature: str
    status: str
    user_id: str
    user_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    title: Optional[str] = None
    provider: Optional[str] = None
    mode: Optional[str] = None
    result_url: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class AdminJobCountsOut(BaseModel):
    queued: int
    running: int
    completed: int
    failed: int
    total: int


class AdminJobMonitorOut(BaseModel):
    counts: AdminJobCountsOut
    jobs: list[AdminJobMonitorItemOut]


# --- Storage inspection & conservative cleanup -------------------------------
class StorageFolderOut(BaseModel):
    name: str
    size_bytes: int
    file_count: int


class StorageLargestFileOut(BaseModel):
    path: str
    size_bytes: int


class AdminStorageOut(BaseModel):
    total_size_bytes: int
    total_file_count: int
    folders: list[StorageFolderOut]
    largest_files: list[StorageLargestFileOut]


class StorageCleanupCandidateOut(BaseModel):
    category: str
    path: str
    size_bytes: int


class StorageCleanupPlanOut(BaseModel):
    candidates: list[StorageCleanupCandidateOut]
    total_candidate_bytes: int
    total_candidate_count: int
    by_category: dict[str, int]
    confirm_phrase: str
    protected: list[str]


class StorageCleanupExecuteIn(BaseModel):
    confirm: str = Field(min_length=1, max_length=64)


class StorageCleanupResultOut(BaseModel):
    executed: bool
    deleted_count: int
    freed_bytes: int
    skipped: list[str]
    message: str


# --- Stale job recovery ------------------------------------------------------
class StaleJobOut(BaseModel):
    id: str
    feature: str
    status: str
    user_id: str
    user_name: Optional[str] = None
    project_id: Optional[str] = None
    title: Optional[str] = None
    created_at: datetime
    elapsed_minutes: int


class StaleJobRef(BaseModel):
    feature: str
    id: str


class MarkStaleIn(BaseModel):
    action: Literal["cancelled", "failed"] = "cancelled"
    threshold_minutes: int = Field(default=60, ge=1, le=100000)
    ids: Optional[list[StaleJobRef]] = None


class MarkStaleResultOut(BaseModel):
    marked: int
    action: str
    note: str
    refunds: int
    details: list[str]


class DismissJobIn(BaseModel):
    feature: str
    id: str


# --- Asset trash (soft delete) -----------------------------------------------
TrashableType = Literal["video", "scene", "generation", "upload"]


class TrashIn(BaseModel):
    entity_type: TrashableType
    entity_id: str
    force_original: bool = False
    force_referenced: bool = False


class TrashItemOut(BaseModel):
    entity_type: str
    entity_id: str
    title: Optional[str] = None
    file_url: Optional[str] = None
    deleted_at: datetime


class TrashResultOut(BaseModel):
    trashed: bool
    entity_type: str
    entity_id: str
    moved_files: list[str]
    message: str


class TrashRestoreIn(BaseModel):
    entity_type: TrashableType
    entity_id: str


class EmptyTrashIn(BaseModel):
    confirm: str = Field(min_length=1, max_length=64)


# --- Auth / accounts ---------------------------------------------------------
class SignupIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=200)
    name: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=255)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class AuthStatusOut(BaseModel):
    public_signup_enabled: bool
    requires_admin_approval: bool


class AdminSetupStatusOut(BaseModel):
    owner_exists: bool
    needs_admin_password: bool
    owner_name: Optional[str] = None


class AdminPasswordSetupIn(BaseModel):
    password: str = Field(min_length=8, max_length=200)
    confirm_password: str = Field(min_length=8, max_length=200)


# --- Avatar & Voice (Phase 16A) ----------------------------------------------
class AvatarAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    avatar_type: str
    source_file_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    status: str
    provider: str
    notes: Optional[str] = None
    created_at: datetime


class VoiceAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    voice_type: str
    provider: str
    sample_file_path: Optional[str] = None
    status: str
    created_at: datetime


class VoiceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    voice_type: Literal["preset", "local_tts", "uploaded_sample"] = "preset"


class AvatarJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    avatar_id: Optional[str] = None
    voice_id: Optional[str] = None
    job_type: str
    script_text: Optional[str] = None
    status: str
    provider: str
    avatar_preset: Optional[str] = None
    avatar_width: Optional[int] = None
    avatar_height: Optional[int] = None
    avatar_frames: Optional[int] = None
    avatar_steps: Optional[int] = None
    avatar_cfg: Optional[float] = None
    avatar_runtime_seconds: Optional[float] = None
    output_video_path: Optional[str] = None
    error_message: Optional[str] = None
    credits_cost: int
    created_at: datetime
    completed_at: Optional[datetime] = None


class GreetingJobIn(BaseModel):
    avatar_id: Optional[str] = None
    voice_id: Optional[str] = None
    script_text: Optional[str] = Field(default=None, max_length=2000)
    avatar_preset: Optional[Literal["tiny_test", "low_vram", "balanced", "quality"]] = None


class AvatarWanPresetOut(BaseModel):
    id: str
    label: str
    description: str
    width: int
    height: int
    frames: int
    steps: int
    cfg: float
    warning: Optional[str] = None
    verified: bool = False
    default: bool = False


class ProviderReadinessOut(BaseModel):
    backend: str
    ready: bool
    detail: str
    # Avatar-only diagnostics (admin view); None for the voice backend.
    comfy_reachable: Optional[bool] = None
    node_present: Optional[bool] = None
    workflow_present: Optional[bool] = None
    models_present: Optional[bool] = None
    missing: list[str] = []


class AvatarVoiceReadinessOut(BaseModel):
    avatar: ProviderReadinessOut
    voice: ProviderReadinessOut
    greeting_text: str
    avatar_enabled: bool
    voice_enabled: bool
    credits_per_avatar_video: int
    credits_per_voice_generation: int
    default_avatar_preset: str
    avatar_presets: list[AvatarWanPresetOut] = Field(default_factory=list)


# --- Provider integrations (admin-only) --------------------------------------
class IntegrationProviderOut(BaseModel):
    id: str
    name: str
    kind: str
    note: str
    enabled: bool
    configured: bool
    masked_key: Optional[str] = None
    last_test_result: Optional[str] = None
    config: dict[str, str] = Field(default_factory=dict)


class IntegrationKeyIn(BaseModel):
    api_key: str = Field(min_length=1, max_length=500)


class IntegrationEnabledIn(BaseModel):
    enabled: bool


class IntegrationConfigIn(BaseModel):
    base_url: Optional[str] = Field(default=None, max_length=500)
    model_id: Optional[str] = Field(default=None, max_length=200)
    create_endpoint: Optional[str] = Field(default=None, max_length=300)
    status_endpoint: Optional[str] = Field(default=None, max_length=300)
    image_model: Optional[str] = Field(default=None, max_length=200)
    image_size: Optional[str] = Field(default=None, max_length=40)
    image_quality: Optional[str] = Field(default=None, max_length=40)
    organization: Optional[str] = Field(default=None, max_length=200)
    project: Optional[str] = Field(default=None, max_length=200)
