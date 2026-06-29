from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..schemas import (
    AdminCreditAdjustmentIn,
    AdminCreditRefundIn,
    AdminCreditTransactionOut,
    AdminDashboardOut,
    AdminJobMonitorOut,
    AdminSafeResetOut,
    AdminStorageOut,
    BackupOut,
    DismissJobIn,
    EmptyTrashIn,
    IntegrationEnabledIn,
    IntegrationConfigIn,
    IntegrationKeyIn,
    IntegrationProviderOut,
    FamilyUserCreate,
    FamilyUserOut,
    FamilyUserUpdate,
    MarkStaleIn,
    MarkStaleResultOut,
    SandboxTopupCreate,
    SandboxTopupOut,
    StaleJobOut,
    StorageCleanupExecuteIn,
    StorageCleanupPlanOut,
    StorageCleanupResultOut,
    TopupPackageOut,
    TrashIn,
    TrashItemOut,
    TrashResultOut,
    TrashRestoreIn,
)
from ..services import (
    admin,
    backups,
    integrations,
    job_monitor,
    stale_jobs,
    storage_admin,
    topups,
    trash,
)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


@router.get("/dashboard", response_model=AdminDashboardOut)
def dashboard(db: Session = Depends(get_db)):
    return admin.build_dashboard(db)


@router.post("/workflow/reset-safe-defaults", response_model=AdminSafeResetOut)
def reset_safe_defaults():
    return admin.reset_safe_workflow_config()


@router.get("/family-users", response_model=list[FamilyUserOut])
def list_family_users(db: Session = Depends(get_db)):
    return admin.list_family_users(db)


@router.post("/family-users", response_model=FamilyUserOut, status_code=201)
def create_family_user(payload: FamilyUserCreate, db: Session = Depends(get_db)):
    return admin.create_family_user(db, payload)


@router.put("/family-users/{user_id}", response_model=FamilyUserOut)
def update_family_user(
    user_id: str, payload: FamilyUserUpdate, db: Session = Depends(get_db)
):
    return admin.update_family_user(db, user_id, payload)


@router.post("/family-users/{user_id}/disable", response_model=FamilyUserOut)
def disable_family_user(user_id: str, db: Session = Depends(get_db)):
    return admin.set_family_user_status(db, user_id, "disabled")


@router.post("/family-users/{user_id}/reactivate", response_model=FamilyUserOut)
def reactivate_family_user(user_id: str, db: Session = Depends(get_db)):
    return admin.set_family_user_status(db, user_id, "active")


@router.get("/credits/transactions", response_model=list[AdminCreditTransactionOut])
def list_credit_transactions(
    user_id: str | None = None,
    transaction_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return admin.list_credit_transactions(
        db,
        user_id=user_id,
        transaction_type=transaction_type,
        status=status,
        limit=limit,
    )


@router.post("/credits/add", response_model=FamilyUserOut)
def add_credits(payload: AdminCreditAdjustmentIn, db: Session = Depends(get_db)):
    return admin.add_credits(db, payload)


@router.post("/credits/remove", response_model=FamilyUserOut)
def remove_credits(payload: AdminCreditAdjustmentIn, db: Session = Depends(get_db)):
    return admin.remove_credits(db, payload)


@router.post(
    "/credits/transactions/{transaction_id}/refund",
    response_model=AdminCreditTransactionOut,
)
def refund_credit_transaction(
    transaction_id: str,
    payload: AdminCreditRefundIn | None = None,
    db: Session = Depends(get_db),
):
    return admin.refund_credit_transaction(
        db,
        transaction_id,
        note=payload.note if payload else None,
    )


# --- Sandbox / test top-ups (no real payment processing) ---------------------
@router.get("/topups/packages", response_model=list[TopupPackageOut])
def list_topup_packages():
    return topups.list_packages()


@router.get("/topups", response_model=list[SandboxTopupOut])
def list_topups(limit: int = 50, db: Session = Depends(get_db)):
    return topups.list_topups(db, limit=limit)


@router.post("/topups/create", response_model=SandboxTopupOut, status_code=201)
def create_topup(payload: SandboxTopupCreate, db: Session = Depends(get_db)):
    return topups.create_topup(db, payload)


@router.post("/topups/{topup_id}/complete", response_model=SandboxTopupOut)
def complete_topup(topup_id: str, db: Session = Depends(get_db)):
    return topups.complete_topup(db, topup_id)


@router.post("/topups/{topup_id}/cancel", response_model=SandboxTopupOut)
def cancel_topup(topup_id: str, db: Session = Depends(get_db)):
    return topups.cancel_topup(db, topup_id)


# --- Local backup & recovery (local-first, manual restore — see README) -------
@router.get("/backups", response_model=list[BackupOut])
def list_backups():
    return backups.list_backups()


@router.post("/backups/create", response_model=BackupOut, status_code=201)
def create_backup():
    return backups.create_backup()


@router.get("/backups/{backup_id}/download")
def download_backup(backup_id: str):
    path = backups.resolve_backup_path(backup_id)
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.delete("/backups/{backup_id}", status_code=204)
def delete_backup(backup_id: str):
    backups.delete_backup(backup_id)


# --- Job monitor (read-only; no retry/clear — see service notes) -------------
@router.get("/jobs", response_model=AdminJobMonitorOut)
def list_jobs(
    status: str | None = None,
    feature: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    return job_monitor.build_job_monitor(db, status=status, feature=feature, limit=limit)


# --- Stale job recovery ------------------------------------------------------
@router.get("/jobs/stale", response_model=list[StaleJobOut])
def list_stale_jobs(threshold_minutes: int = 60, db: Session = Depends(get_db)):
    return stale_jobs.list_stale(db, threshold_minutes)


@router.post("/jobs/mark-stale", response_model=MarkStaleResultOut)
def mark_stale_jobs(payload: MarkStaleIn, db: Session = Depends(get_db)):
    return stale_jobs.mark_stale(
        db,
        action=payload.action,
        threshold_minutes=payload.threshold_minutes,
        ids=payload.ids,
    )


@router.post("/jobs/dismiss")
def dismiss_job(payload: DismissJobIn, db: Session = Depends(get_db)):
    return stale_jobs.dismiss_job(db, payload.feature, payload.id)


# --- Asset trash (selective, recoverable soft delete) ------------------------
@router.get("/trash", response_model=list[TrashItemOut])
def list_trash(db: Session = Depends(get_db)):
    return trash.list_trash(db)


@router.post("/trash", response_model=TrashResultOut)
def trash_asset(payload: TrashIn, db: Session = Depends(get_db)):
    return trash.move_to_trash(
        db,
        payload.entity_type,
        payload.entity_id,
        force_original=payload.force_original,
        force_referenced=payload.force_referenced,
    )


@router.post("/trash/restore", response_model=TrashResultOut)
def restore_asset(payload: TrashRestoreIn, db: Session = Depends(get_db)):
    return trash.restore(db, payload.entity_type, payload.entity_id)


@router.post("/trash/empty")
def empty_trash(payload: EmptyTrashIn, db: Session = Depends(get_db)):
    return trash.empty_trash(db, payload.confirm)


# --- Optional premium provider integrations (admin-only; keys never exposed) --
@router.get("/integrations", response_model=list[IntegrationProviderOut])
def list_integrations():
    return integrations.list_providers()


@router.post("/integrations/{provider}/key", response_model=list[IntegrationProviderOut])
def set_integration_key(provider: str, payload: IntegrationKeyIn):
    return integrations.set_key(provider, payload.api_key)


@router.delete("/integrations/{provider}/key", response_model=list[IntegrationProviderOut])
def delete_integration_key(provider: str):
    return integrations.delete_key(provider)


@router.post("/integrations/{provider}/enabled", response_model=list[IntegrationProviderOut])
def set_integration_enabled(provider: str, payload: IntegrationEnabledIn):
    return integrations.set_enabled(provider, payload.enabled)


@router.post("/integrations/{provider}/config", response_model=list[IntegrationProviderOut])
def set_integration_config(provider: str, payload: IntegrationConfigIn):
    return integrations.set_config(provider, payload.model_dump(exclude_none=True))


@router.post("/integrations/{provider}/test")
def test_integration(provider: str):
    return integrations.test_connection(provider)


# --- Storage inspection & conservative cleanup -------------------------------
@router.get("/storage", response_model=AdminStorageOut)
def storage_report():
    return storage_admin.build_storage_report()


@router.post("/storage/cleanup/plan", response_model=StorageCleanupPlanOut)
def storage_cleanup_plan(db: Session = Depends(get_db)):
    return storage_admin.build_cleanup_plan(db)


@router.post("/storage/cleanup/execute", response_model=StorageCleanupResultOut)
def storage_cleanup_execute(
    payload: StorageCleanupExecuteIn, db: Session = Depends(get_db)
):
    return storage_admin.execute_cleanup(db, payload.confirm)
