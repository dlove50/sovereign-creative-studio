"""Authentication, avatar, voice, and provider-integration schemas."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .schema_types import *  # noqa: F403 - schema facade intentionally re-exports literals
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
