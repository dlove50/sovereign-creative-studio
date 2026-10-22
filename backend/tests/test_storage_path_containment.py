"""Containment contract for the /storage/ URL -> local path mappers.

Several modules map a public "/storage/..." URL onto a filesystem path. They
must all refuse to leave STORAGE_DIR: traversal segments, and absolute
components (an absolute right-hand side replaces the left when joined with /).

These mappers are deliberately not resolve()d, because export folders can be
junctions and resolving them would reject legitimate reads. So the containment
check is lexical, and these tests pin that behaviour.
"""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

from app.config import STORAGE_DIR  # noqa: E402
from app.services.asset_jobs import _storage_path_from_url  # noqa: E402
from app.services.exports import storage_path_for  # noqa: E402

ESCAPES = [
    "/storage/../secret.txt",
    "/storage/uploads/../../secret.txt",
    "/storage//etc/passwd",
]


def test_storage_path_for_maps_nested_path():
    assert storage_path_for("/storage/uploads/source.png") == (
        STORAGE_DIR / "uploads" / "source.png"
    )


def test_storage_path_for_returns_none_for_non_storage_urls():
    assert storage_path_for(None) is None
    assert storage_path_for("") is None
    assert storage_path_for("/uploads/source.png") is None
    assert storage_path_for("https://example.com/storage/source.png") is None


@pytest.mark.parametrize("url", ESCAPES)
def test_storage_path_for_refuses_to_escape_storage(url):
    assert storage_path_for(url) is None


def test_storage_path_from_url_maps_nested_path():
    assert _storage_path_from_url("/storage/uploads/source.png") == (
        STORAGE_DIR / "uploads" / "source.png"
    )


@pytest.mark.parametrize("url", ESCAPES)
def test_storage_path_from_url_refuses_to_escape_storage(url):
    with pytest.raises(ValueError):
        _storage_path_from_url(url)


def test_storage_path_from_url_rejects_non_storage_prefix():
    with pytest.raises(ValueError):
        _storage_path_from_url("/uploads/source.png")
