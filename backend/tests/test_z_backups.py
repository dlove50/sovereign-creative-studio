"""Phase 6: local backup & recovery (timestamped ZIP snapshots, manual restore)."""
import io
import os
import sys
import tempfile
import zipfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _zip_names(client, backup_id):
    resp = client.get(f"/api/admin/backups/{backup_id}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        return zf.namelist(), zf


def test_create_backup_makes_zip_with_manifest(client):
    # Seed a known storage file so we can prove storage/ is captured.
    (config.STORAGE_DIR / "workflow_config.json").write_text(
        '{"image_model": "flux-kontext", "video_backend": "mock"}', encoding="utf-8"
    )
    out = client.post("/api/admin/backups/create").json()
    assert out["filename"].endswith(".zip")
    assert out["size_bytes"] > 0
    assert out["download_url"].endswith("/download")

    resp = client.get(f"/api/admin/backups/{out['id']}/download")
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        assert "backup_manifest.json" in names
        manifest = __import__("json").loads(zf.read("backup_manifest.json"))
    assert manifest["app_name"] == "Sovereign Creative Studio"
    assert manifest["backup_id"] == out["id"]
    assert "created_at" in manifest
    assert isinstance(manifest["included"], list) and manifest["included"]
    assert "safe_config" in manifest
    # DB + workflow config captured.
    assert any(n.endswith(".db") for n in names)
    assert "backend/storage/workflow_config.json" in names


def test_expected_files_included_when_present(client):
    out = client.post("/api/admin/backups/create").json()
    names, _ = _zip_names(client, out["id"])
    # README and at least one workflow template are bundled when present.
    assert "README.md" in names
    assert any(n.startswith("backend/workflows/") for n in names)


def test_env_files_are_never_included(client):
    out = client.post("/api/admin/backups/create").json()
    names, _ = _zip_names(client, out["id"])
    assert "backend/.env" not in names
    assert "frontend/.env.local" not in names
    assert not any(n.endswith(".env") or ".env." in n for n in names)


def test_backups_folder_is_not_recursively_included(client):
    # An earlier backup already exists in storage/backups; a new one must not
    # nest it (or any backups/ content) inside itself.
    out = client.post("/api/admin/backups/create").json()
    names, _ = _zip_names(client, out["id"])
    assert not any(n.startswith("backend/storage/backups/") for n in names)


def test_list_backups_returns_created(client):
    created = client.post("/api/admin/backups/create").json()
    listed = client.get("/api/admin/backups").json()
    assert any(b["id"] == created["id"] for b in listed)
    for b in listed:
        assert b["filename"].endswith(".zip")
        assert b["size_bytes"] > 0


def test_download_unknown_is_404(client):
    assert client.get("/api/admin/backups/scs-backup-nope/download").status_code == 404


def test_download_rejects_path_traversal(client):
    # FastAPI will not route a slash-bearing id, but a traversal-looking id
    # without slashes must be rejected by validation, not served.
    assert client.get("/api/admin/backups/..%2F..%2Fsovereign/download").status_code in (400, 404)


def test_delete_backup_removes_only_that_zip(client):
    out = client.post("/api/admin/backups/create").json()
    assert client.delete(f"/api/admin/backups/{out['id']}").status_code == 204
    listed = client.get("/api/admin/backups").json()
    assert not any(b["id"] == out["id"] for b in listed)
