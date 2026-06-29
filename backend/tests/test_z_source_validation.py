"""Backend (second-line) validation of user-supplied source media URLs."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest
from fastapi import HTTPException

from app import config
from app.services.source_validation import IMAGE_EXTS, VIDEO_EXTS, validate_source_media_url


def _make_storage_file(rel: str) -> str:
    path = config.STORAGE_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return f"/storage/{rel}"


def test_rejects_windows_path():
    with pytest.raises(HTTPException) as exc:
        validate_source_media_url(r"C:\Users\David\Pictures\3d dog.png", allowed_exts=IMAGE_EXTS)
    assert exc.value.status_code == 400 and "Windows paths" in exc.value.detail


def test_rejects_path_traversal():
    with pytest.raises(HTTPException) as exc:
        validate_source_media_url("/storage/../etc/passwd", allowed_exts=IMAGE_EXTS)
    assert exc.value.status_code == 400 and "traversal" in exc.value.detail.lower()


def test_rejects_external_url():
    with pytest.raises(HTTPException) as exc:
        validate_source_media_url("https://evil.com/malware.png", allowed_exts=IMAGE_EXTS)
    assert exc.value.status_code == 400 and "External URLs" in exc.value.detail


def test_rejects_non_storage_path():
    with pytest.raises(HTTPException) as exc:
        validate_source_media_url("/etc/passwd", allowed_exts=None)
    assert exc.value.status_code == 400


def test_rejects_empty():
    with pytest.raises(HTTPException) as exc:
        validate_source_media_url("", allowed_exts=IMAGE_EXTS)
    assert exc.value.status_code == 400


def test_rejects_wrong_file_type():
    url = _make_storage_file("videos/clip.mp4")
    with pytest.raises(HTTPException) as exc:
        validate_source_media_url(url, allowed_exts=IMAGE_EXTS)
    assert exc.value.status_code == 400 and "not compatible" in exc.value.detail


def test_rejects_missing_file_when_existence_required():
    with pytest.raises(HTTPException) as exc:
        validate_source_media_url(
            "/storage/generated/does-not-exist.png", allowed_exts=IMAGE_EXTS, require_exists=True
        )
    assert exc.value.status_code == 400 and "not found" in exc.value.detail.lower()


def test_accepts_valid_storage_image():
    url = _make_storage_file("generated/ok.png")
    assert validate_source_media_url(url, allowed_exts=IMAGE_EXTS) == url


def test_accepts_valid_storage_video():
    url = _make_storage_file("videos/ok.mp4")
    assert validate_source_media_url(url, allowed_exts=VIDEO_EXTS) == url
