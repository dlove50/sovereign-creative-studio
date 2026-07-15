"""Workflow-manager and local administration schemas."""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .schema_types import *  # noqa: F403 - schema facade intentionally re-exports literals
from .schemas_workflows import ModelManagerStatusOut, StatusOut
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
