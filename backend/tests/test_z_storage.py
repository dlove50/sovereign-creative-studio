"""Phase 7: storage inspection + conservative, dry-run-first cleanup."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

CONFIRM = "DELETE_SAFE_CANDIDATES"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _seed():
    s = config.STORAGE_DIR
    (s / "tmp").mkdir(parents=True, exist_ok=True)
    (s / "tmp" / "scratch.bin").write_bytes(b"x" * 100)
    (s / "_testcache").mkdir(parents=True, exist_ok=True)
    (s / "_testcache" / "t.bin").write_bytes(b"y" * 50)
    (s / "exports").mkdir(parents=True, exist_ok=True)
    (s / "exports" / "old-bundle.zip").write_bytes(b"z" * 200)
    (s / "uploads").mkdir(parents=True, exist_ok=True)
    (s / "uploads" / "keep-me.png").write_bytes(b"PNGDATA" * 100)


def test_storage_report_renders(client):
    _seed()
    data = client.get("/api/admin/storage").json()
    assert data["total_size_bytes"] > 0
    assert data["total_file_count"] >= 4
    names = {f["name"] for f in data["folders"]}
    assert "uploads" in names and "tmp" in names
    assert all(not f["path"].endswith("workflow_config.json") for f in data["largest_files"])


def test_cleanup_plan_lists_safe_candidates_only(client):
    _seed()
    plan = client.post("/api/admin/storage/cleanup/plan").json()
    assert plan["confirm_phrase"] == CONFIRM
    paths = {c["path"] for c in plan["candidates"]}
    assert "tmp/scratch.bin" in paths
    assert "_testcache/t.bin" in paths
    assert "exports/old-bundle.zip" in paths
    # Original uploads must never be a cleanup candidate.
    assert not any(p.startswith("uploads/") for p in paths)
    assert plan["by_category"]
    assert any("upload" in note.lower() for note in plan["protected"])


def test_old_backups_keep_newest(client):
    bdir = config.STORAGE_DIR / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    # Deterministic state: control exactly which backups exist (temp storage).
    for existing in bdir.glob("*.zip"):
        existing.unlink()
    for i in range(7):
        p = bdir / f"scs-backup-2026010{i}-000000.zip"
        p.write_bytes(b"b" * 10)
        os.utime(p, (1000 + i * 10, 1000 + i * 10))
    plan = client.post("/api/admin/storage/cleanup/plan").json()
    old = [c for c in plan["candidates"] if c["category"] == "old_backups"]
    # 7 backups, keep newest 5 => exactly 2 are cleanup candidates.
    assert len(old) == 2


def test_execute_requires_confirm_phrase(client):
    _seed()
    assert (
        client.post("/api/admin/storage/cleanup/execute", json={"confirm": "nope"}).status_code
        == 400
    )


def test_execute_deletes_safe_and_protects_uploads(client):
    _seed()
    upload = config.STORAGE_DIR / "uploads" / "keep-me.png"
    assert upload.is_file()
    res = client.post(
        "/api/admin/storage/cleanup/execute", json={"confirm": CONFIRM}
    ).json()
    assert res["executed"] is True
    assert res["deleted_count"] >= 3
    assert res["freed_bytes"] > 0
    # Original upload is protected and survives cleanup.
    assert upload.is_file()
    # Seeded scratch is gone.
    assert not (config.STORAGE_DIR / "tmp" / "scratch.bin").is_file()
    assert not (config.STORAGE_DIR / "exports" / "old-bundle.zip").is_file()
