"""Local storage inspection and conservative, dry-run-first cleanup.

Reports storage usage and proposes ONLY safe deletion candidates: tmp scratch,
`_test*` artifacts, regenerable export bundles, and backups beyond a keep count.
It never proposes (and execution re-validates against) original uploads, active
generated assets, the database, workflow config, .env files, the newest backups,
or any file referenced by a database record. Execution requires an explicit
confirmation phrase. Local-first — no cloud, no scheduled jobs.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..models import Generation, ProductAsset, ProductSceneGeneration, VideoGeneration
from ..schemas import (
    AdminStorageOut,
    StorageCleanupCandidateOut,
    StorageCleanupPlanOut,
    StorageCleanupResultOut,
    StorageFolderOut,
    StorageLargestFileOut,
)

CONFIRM_PHRASE = "DELETE_SAFE_CANDIDATES"
KEEP_BACKUPS = 5
_STORAGE_URL_PREFIX = "/storage/"
_LARGEST_FILE_COUNT = 15

# Top-level storage folders holding protected live data — never cleanup candidates.
_PROTECTED_DIRS = {
    "uploads",  # original uploads — never deleted in this phase
    "processed",
    "product-scenes",
    "videos",
    "mask-previews",
    "pose_presets",
}
# Protected files at the storage root (config). The DB and .env live outside storage.
_PROTECTED_ROOT_FILES = {"workflow_config.json"}
# Sensitive files kept out of the "largest files" listing.
_SENSITIVE_NAMES = {"workflow_config.json"}

_PROTECTED_SUMMARY = [
    "Original uploads (storage/uploads/)",
    "Active generated assets (processed/, product-scenes/, videos/, mask-previews/)",
    "Bundled pose presets (pose_presets/)",
    "Workflow config (workflow_config.json), the database, and .env files",
    f"The newest {KEEP_BACKUPS} backups",
    "Any file referenced by a database record",
]


def _storage() -> Path:
    return config.STORAGE_DIR


def _iter_files(root: Path):
    """Yield every file under root, skipping unreadable dirs (e.g. locked tmp)."""
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        for name in filenames:
            yield Path(dirpath) / name


def _safe_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def build_storage_report() -> AdminStorageOut:
    root = _storage()
    total_size = 0
    total_count = 0
    folders: dict[str, dict[str, int]] = {}
    largest: list[tuple[int, str]] = []

    for path in _iter_files(root):
        size = _safe_size(path)
        if size is None:
            continue
        rel = path.relative_to(root)
        top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        bucket = folders.setdefault(top, {"size": 0, "count": 0})
        bucket["size"] += size
        bucket["count"] += 1
        total_size += size
        total_count += 1
        if path.name not in _SENSITIVE_NAMES:
            largest.append((size, rel.as_posix()))

    largest.sort(key=lambda item: item[0], reverse=True)
    folder_out = [
        StorageFolderOut(name=name, size_bytes=info["size"], file_count=info["count"])
        for name, info in sorted(folders.items(), key=lambda kv: kv[1]["size"], reverse=True)
    ]
    return AdminStorageOut(
        total_size_bytes=total_size,
        total_file_count=total_count,
        folders=folder_out,
        largest_files=[
            StorageLargestFileOut(path=p, size_bytes=s) for s, p in largest[:_LARGEST_FILE_COUNT]
        ],
    )


def _referenced_paths(db: Session) -> set[Path]:
    """Resolved local paths of every storage file referenced by a DB record."""
    root = _storage()
    urls: list[str | None] = []
    urls += [r.file_url for r in db.scalars(select(Generation)).all()]
    urls += [r.result_url for r in db.scalars(select(ProductSceneGeneration)).all()]
    urls += [r.result_url for r in db.scalars(select(VideoGeneration)).all()]
    for a in db.scalars(select(ProductAsset)).all():
        urls += [a.original_url, a.processed_url, a.mask_url]

    referenced: set[Path] = set()
    for url in urls:
        if url and url.startswith(_STORAGE_URL_PREFIX):
            referenced.add((root / url[len(_STORAGE_URL_PREFIX):]).resolve())
    return referenced


def _newest_backup_names() -> set[str]:
    backups_dir = _storage() / "backups"
    if not backups_dir.is_dir():
        return set()
    zips = sorted(
        backups_dir.glob("*.zip"),
        key=lambda p: (_safe_size_mtime(p)),
        reverse=True,
    )
    return {p.name for p in zips[:KEEP_BACKUPS]}


def _safe_size_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _candidate_files(root: Path) -> list[tuple[str, Path]]:
    """(category, path) for every safe candidate, before reference/keep filtering."""
    out: list[tuple[str, Path]] = []

    tmp = root / "tmp"
    if tmp.is_dir():
        out += [("tmp", p) for p in _iter_files(tmp)]

    # Top-level `_test*` artifacts (files directly or under such a folder).
    for entry in root.iterdir() if root.is_dir() else []:
        if entry.name.startswith("_test"):
            if entry.is_dir():
                out += [("test_artifacts", p) for p in _iter_files(entry)]
            elif entry.is_file():
                out.append(("test_artifacts", entry))

    exports = root / "exports"
    if exports.is_dir():
        out += [("exports", p) for p in _iter_files(exports)]

    backups_dir = root / "backups"
    if backups_dir.is_dir():
        keep = _newest_backup_names()
        for p in backups_dir.glob("*.zip"):
            if p.name not in keep:
                out.append(("old_backups", p))

    return out


def build_cleanup_plan(db: Session) -> StorageCleanupPlanOut:
    root = _storage()
    referenced = _referenced_paths(db)
    candidates: list[StorageCleanupCandidateOut] = []
    by_category: dict[str, int] = {}
    total_bytes = 0

    for category, path in _candidate_files(root):
        if not path.is_file():
            continue
        if path.resolve() in referenced:  # defensive: never touch referenced files
            continue
        size = _safe_size(path)
        if size is None:
            continue
        rel = path.relative_to(root).as_posix()
        candidates.append(
            StorageCleanupCandidateOut(category=category, path=rel, size_bytes=size)
        )
        by_category[category] = by_category.get(category, 0) + 1
        total_bytes += size

    candidates.sort(key=lambda c: c.size_bytes, reverse=True)
    return StorageCleanupPlanOut(
        candidates=candidates,
        total_candidate_bytes=total_bytes,
        total_candidate_count=len(candidates),
        by_category=by_category,
        confirm_phrase=CONFIRM_PHRASE,
        protected=_PROTECTED_SUMMARY,
    )


def _is_protected(path: Path, root: Path, keep_backups: set[str]) -> bool:
    rel = path.relative_to(root)
    if len(rel.parts) == 1:
        return rel.parts[0] in _PROTECTED_ROOT_FILES
    top = rel.parts[0]
    if top in _PROTECTED_DIRS:
        return True
    if top == "backups":
        return path.name in keep_backups
    return False


def execute_cleanup(db: Session, confirm: str) -> StorageCleanupResultOut:
    if confirm != CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f"Confirmation phrase required to execute cleanup (expected '{CONFIRM_PHRASE}').",
        )

    root = _storage()
    root_resolved = root.resolve()
    referenced = _referenced_paths(db)
    keep_backups = _newest_backup_names()
    plan = build_cleanup_plan(db)

    deleted_count = 0
    freed_bytes = 0
    skipped: list[str] = []

    for candidate in plan.candidates:
        path = (root / candidate.path).resolve()
        # Re-validate every guard at execution time, not just at planning.
        if root_resolved not in path.parents:
            skipped.append(candidate.path)
            continue
        if _is_protected(path, root, keep_backups) or path in referenced:
            skipped.append(candidate.path)
            continue
        size = _safe_size(path)
        try:
            path.unlink()
        except OSError:
            skipped.append(candidate.path)
            continue
        deleted_count += 1
        freed_bytes += size or 0

    message = (
        f"Deleted {deleted_count} safe file(s), freed {freed_bytes} bytes."
        if deleted_count
        else "No files were deleted."
    )
    if skipped:
        message += f" Skipped {len(skipped)} (protected, referenced, or locked)."
    return StorageCleanupResultOut(
        executed=True,
        deleted_count=deleted_count,
        freed_bytes=freed_bytes,
        skipped=skipped,
        message=message,
    )
