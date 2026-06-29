"""Second line of defense: validate user-supplied source media URLs server-side.

Frontend validation runs first, but a crafted request must still be rejected here.
Only same-origin /storage/... paths that resolve inside STORAGE_DIR are accepted;
Windows paths, traversal, external URLs and wrong file types return HTTP 400 (the
caller must create no job and charge no credits).
"""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from ..config import STORAGE_DIR

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}

_WINDOWS_PATH = re.compile(r"^[A-Za-z]:\\")
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")


def validate_source_media_url(
    url: str | None, *, allowed_exts: set[str] | None, require_exists: bool = False
) -> str:
    value = (url or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="A source media file is required.")
    if _WINDOWS_PATH.match(value):
        raise HTTPException(
            status_code=400,
            detail="Windows paths are not accepted here. Upload the file or choose it from Assets.",
        )
    if ".." in value:
        raise HTTPException(status_code=400, detail="Path traversal is not allowed.")
    if _SCHEME.match(value) or value.startswith("//"):
        raise HTTPException(
            status_code=400,
            detail="External URLs are not accepted. Upload the file or choose from Assets.",
        )
    if not value.startswith("/storage/"):
        raise HTTPException(
            status_code=400,
            detail="External URLs are not accepted. Upload the file or choose from Assets.",
        )
    relative = value[len("/storage/"):]
    candidate = (STORAGE_DIR / relative).resolve()
    try:
        candidate.relative_to(STORAGE_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path traversal is not allowed.") from exc
    if allowed_exts is not None and candidate.suffix.lower() not in allowed_exts:
        raise HTTPException(status_code=400, detail="This file type is not compatible with this tool.")
    if require_exists and not candidate.is_file():
        raise HTTPException(status_code=400, detail="Source file was not found.")
    return value
