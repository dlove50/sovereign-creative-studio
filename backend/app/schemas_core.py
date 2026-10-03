"""Core project, image, product-scene, copy, and campaign schemas."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .schema_types import *  # noqa: F403 - schema facade intentionally re-exports literals
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
    # Local Image Edit only: up to two more /storage images to borrow an outfit or place from.
    reference_image_urls: list[str] = Field(default_factory=list, max_length=2)
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
