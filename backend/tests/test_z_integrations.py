"""Phase 14 shell: admin provider integrations — keys stored server-side, masked,
never exposed to the browser, excluded from backups."""
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

from app.main import app

SECRET = "sk-supersecret-key-1234567890"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_providers_listed_with_local_defaults_unchanged(client):
    providers = {p["id"]: p for p in client.get("/api/admin/integrations").json()}
    assert {"seedance", "openai"} <= set(providers)
    assert all(p["enabled"] is False for p in providers.values())  # off by default
    assert all("may cost money" in p["note"] for p in providers.values())


def test_key_is_masked_and_never_exposed(client):
    out = client.post("/api/admin/integrations/openai/key", json={"api_key": SECRET}).json()
    openai = next(p for p in out if p["id"] == "openai")
    assert openai["configured"] is True
    assert openai["masked_key"] and SECRET not in openai["masked_key"]
    assert "•" in openai["masked_key"]
    # The raw key must never appear anywhere in the API response body.
    assert SECRET not in client.get("/api/admin/integrations").text


def test_enable_requires_key_then_toggles(client):
    # seedance has no key yet -> cannot enable.
    blocked = client.post("/api/admin/integrations/seedance/enabled", json={"enabled": True})
    assert blocked.status_code == 400
    client.post("/api/admin/integrations/seedance/key", json={"api_key": "cdance-abc-999"})
    ok = client.post("/api/admin/integrations/seedance/enabled", json={"enabled": True}).json()
    assert next(p for p in ok if p["id"] == "seedance")["enabled"] is True


def test_delete_key_disables_provider(client):
    client.post("/api/admin/integrations/openai/key", json={"api_key": SECRET})
    out = client.delete("/api/admin/integrations/openai/key").json()
    openai = next(p for p in out if p["id"] == "openai")
    assert openai["configured"] is False and openai["enabled"] is False


def test_secrets_excluded_from_backup(client):
    client.post("/api/admin/integrations/openai/key", json={"api_key": SECRET})
    created = client.post("/api/admin/backups/create").json()
    raw = client.get(f"/api/admin/backups/{created['id']}/download").content
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        # No secrets/ entries, and the raw key is nowhere in the archive bytes.
        assert not any("secrets/" in n for n in names)
    assert SECRET.encode() not in raw
