"""Local backup and recovery for the private/family build.

Creates timestamped ZIP snapshots of the SQLite database, generated storage,
workflow configuration, and key local project files. Local-first: no cloud, no
external services, no scheduled jobs. Backup is read-only over live data —
nothing is moved or deleted while a snapshot is taken. Restore is intentionally
manual (documented in the README); there is no automatic destructive restore.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import uuid
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from .. import config
from ..schemas import BackupOut

APP_NAME = "Sovereign Creative Studio"

# Backups default under storage/backups so they travel with the data folder and
# are never recursively included in a new backup.
#
# That default is also inside the directory main.py mounts at /storage, so
# GET /storage/backups/<name>.zip returns a full backup -- the SQLite database
# with every account, password hash and credit balance, plus every generated
# file -- to anyone who can reach the port. Worse than the generated media
# sitting beside it: those have UUID names that have to leak, while a backup is
# named scs-backup-YYYYMMDD-HHMMSS and can simply be guessed.
#
# BACKUP_DIR makes the location movable without touching code, which is what
# tools/harden-sovereign.sh sets. The default is left as it was so existing
# backups stay visible in the UI rather than silently disappearing.
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(config.STORAGE_DIR / "backups")))

_BACKUP_PREFIX = "scs-backup-"
# Top-level storage/ folders we never copy into a backup: the backups folder
# itself (recursion), scratch/cache space (transient, sometimes lock-held), and
# `secrets/` (session key + provider API keys must never be written to a backup).
_EXCLUDED_STORAGE_DIRS = {"backups", "tmp", "secrets"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _project_root() -> Path:
    # config.BASE_DIR is the backend/ dir; the studio root is its parent.
    return config.BASE_DIR.parent


def _db_path() -> Path | None:
    prefix = "sqlite:///"
    url = config.DATABASE_URL
    if not url.startswith(prefix):
        return None
    return Path(url[len(prefix):])


def _safe_config_summary() -> dict[str, str]:
    summary = {
        "generator_backend": config.GENERATOR_BACKEND,
        "product_scene_backend": config.PRODUCT_SCENE_BACKEND,
        "product_scene_model": config.PRODUCT_SCENE_MODEL or "(unset)",
        "product_scene_mode": config.COMFYUI_PRODUCT_SCENE_MODE,
        "video_backend": config.VIDEO_BACKEND,
        "comfyui_base_url": config.COMFYUI_BASE_URL,
    }
    wf = config.STORAGE_DIR / "workflow_config.json"
    if wf.is_file():
        try:
            data = json.loads(wf.read_text(encoding="utf-8"))
            for key, value in data.items():
                summary[f"workflow.{key}"] = str(value)
        except Exception:  # noqa: BLE001 - a bad config file must not block backups.
            pass
    return summary


def _walk_storage(storage: Path):
    """Yield (file_path, arcname) for storage/, pruning excluded top-level dirs.

    os.walk lets us prune dirnames in place so we never descend into the backups
    or tmp folders (the latter can hold OS-locked scratch files)."""
    for dirpath, dirnames, filenames in os.walk(storage, onerror=lambda _err: None):
        rel_dir = Path(dirpath).relative_to(storage)
        if rel_dir == Path("."):
            dirnames[:] = [
                d
                for d in dirnames
                if d not in _EXCLUDED_STORAGE_DIRS and not d.startswith("_test")
            ]
        for name in filenames:
            src = Path(dirpath) / name
            rel = src.relative_to(storage).as_posix()
            yield src, f"backend/storage/{rel}"


def _collect_entries(db_snapshot: Path | None = None) -> list[tuple[Path, str]]:
    """Build the (source, arcname) list, including each item only when present.

    Arcnames mirror the live layout (backend/..., frontend/...) so a manual
    restore is an obvious copy-back."""
    root = _project_root()
    entries: list[tuple[Path, str]] = []

    db = _db_path()
    if db and db.is_file():
        entries.append((db_snapshot or db, f"backend/{db.name}"))

    storage = config.STORAGE_DIR
    if storage.is_dir():
        # workflow_config.json rides along here (it lives in storage/).
        entries.extend(_walk_storage(storage))

    # Never include environment files: they may contain provider keys, session
    # secrets, or machine-specific settings. The manifest stores only a safe
    # non-secret config summary for restore guidance.
    for src, arc in (
        (root / "README.md", "README.md"),
    ):
        if src.is_file():
            entries.append((src, arc))

    workflows = config.BASE_DIR / "workflows"
    if workflows.is_dir():
        for path in sorted(workflows.rglob("*")):
            if path.is_file():
                rel = path.relative_to(workflows).as_posix()
                entries.append((path, f"backend/workflows/{rel}"))

    return entries


def _snapshot_sqlite_database(source: Path, destination: Path) -> None:
    """Create a transactionally consistent copy of a live SQLite database.

    Copying the database file directly can miss committed pages that still live
    in its WAL file. SQLite's online backup API reads one coherent database
    snapshot while allowing normal application reads and writes to continue.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    # sqlite3.Connection's context manager commits/rolls back but does not close;
    # closing is required so Windows releases the staged database file promptly.
    with closing(sqlite3.connect(str(source))) as source_db, closing(
        sqlite3.connect(str(destination))
    ) as snapshot_db:
        source_db.backup(snapshot_db)
        check = snapshot_db.execute("PRAGMA quick_check").fetchone()
        if not check or check[0] != "ok":
            raise RuntimeError("SQLite backup snapshot failed its integrity check")


def create_backup() -> BackupOut:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    created = _now()
    backup_id = f"{_BACKUP_PREFIX}{created.strftime('%Y%m%d-%H%M%S')}"
    zip_path = BACKUP_DIR / f"{backup_id}.zip"
    if zip_path.exists():  # two backups in the same second
        backup_id = f"{backup_id}-{uuid.uuid4().hex[:6]}"
        zip_path = BACKUP_DIR / f"{backup_id}.zip"

    # Stage both the SQLite snapshot and archive under the excluded backups/
    # folder. Only move the completed ZIP into place, so a failed backup never
    # appears in the UI as a valid restore point.
    with tempfile.TemporaryDirectory(prefix=".scs-backup-staging-", dir=BACKUP_DIR) as staging_name:
        staging = Path(staging_name)
        db = _db_path()
        db_snapshot = None
        if db and db.is_file():
            db_snapshot = staging / db.name
            _snapshot_sqlite_database(db, db_snapshot)

        included: list[str] = []
        staged_zip = staging / zip_path.name
        with zipfile.ZipFile(staged_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for src, arc in _collect_entries(db_snapshot=db_snapshot):
                try:
                    zf.write(src, arc)
                except (OSError, PermissionError):
                    if db_snapshot is not None and src == db_snapshot:
                        raise
                    # A single locked/transient media file must not abort the
                    # snapshot. The database itself was already verified above.
                    continue
                included.append(arc)
            manifest = {
                "app_name": APP_NAME,
                "backup_id": backup_id,
                "created_at": created.isoformat(),
                "database_snapshot": "sqlite_online_backup" if db_snapshot else "not_applicable",
                "included": included,
                "safe_config": _safe_config_summary(),
            }
            zf.writestr("backup_manifest.json", json.dumps(manifest, indent=2))
        staged_zip.replace(zip_path)

    return _info(zip_path)


def list_backups() -> list[BackupOut]:
    if not BACKUP_DIR.is_dir():
        return []
    infos = [_info(p) for p in BACKUP_DIR.glob(f"{_BACKUP_PREFIX}*.zip")]
    infos.sort(key=lambda i: i.created_at, reverse=True)
    return infos


def resolve_backup_path(backup_id: str) -> Path:
    # Strict id form + containment check prevents path traversal.
    if not re.fullmatch(r"[A-Za-z0-9._-]+", backup_id):
        raise HTTPException(status_code=400, detail="Invalid backup id")
    path = (BACKUP_DIR / f"{backup_id}.zip").resolve()
    if BACKUP_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid backup id")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")
    return path


def delete_backup(backup_id: str) -> None:
    # Only ever removes a validated file inside BACKUP_DIR — never live data.
    resolve_backup_path(backup_id).unlink()


def _info(path: Path) -> BackupOut:
    stat = path.stat()
    return BackupOut(
        id=path.stem,
        filename=path.name,
        created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        size_bytes=stat.st_size,
        download_url=f"/api/admin/backups/{path.stem}/download",
    )
