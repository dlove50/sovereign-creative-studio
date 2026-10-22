"""Credit invariants for base image generation.

The video path already pins these in test_z_video_credits.py; the image path
did not, even though it is the one that runs through ComfyUI and so the one
that will start failing when the GPU is unavailable or a render exceeds the
poll budget. On AiServerR9700 that is not hypothetical.

Two properties are worth money:

* a failed generation is never charged (charge-on-completion), and
* completing twice does not charge twice -- `_complete_generation` guards on an
  existing generation_charge for the same related_id, and a retry or a
  duplicated worker run must not bypass it.
"""
import os
import sys
import tempfile
import time

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.generation_jobs as generation_jobs  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Generation  # noqa: E402

HEADER = "X-SCS-Family-User-Id"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _user(client, name, credits=100):
    return client.post(
        "/api/admin/family-users",
        json={"display_name": name, "role": "family_user", "initial_credits": credits},
    ).json()


def _balance(client, user_id):
    return client.get("/api/me", headers={HEADER: user_id}).json()["credits"]


def _charges(client, user_id, related_id):
    rows = client.get("/api/admin/credits/transactions").json()
    return [
        r for r in rows
        if r.get("related_id") == related_id
        and r.get("transaction_type") == "generation_charge"
    ]


def _project(client, user_id):
    return client.post(
        "/api/projects", json={"name": "Credit Project"},
        headers={HEADER: user_id},
    ).json()


def _generate(client, user_id, project_id):
    return client.post(
        "/api/generations",
        json={"project_id": project_id, "prompt": "a test image",
              "media_type": "image"},
        headers={HEADER: user_id},
    )


def _wait(client, user_id, gen_id, want, timeout=10.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        latest = client.get(f"/api/generations/{gen_id}",
                            headers={HEADER: user_id}).json()
        if latest.get("status") == want:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"generation never reached {want!r}; last was {latest}")


def test_failed_generation_is_not_charged(client, monkeypatch):
    """A backend failure -- including a ComfyUI timeout -- must cost nothing."""
    class _Boom:
        async def generate(self, **kwargs):
            raise RuntimeError("simulated ComfyUI failure")

    monkeypatch.setattr(generation_jobs, "get_generator",
                        lambda *a, **k: _Boom())
    u = _user(client, "Image Failure Member")
    project = _project(client, u["id"])
    gen_id = _generate(client, u["id"], project["id"]).json()["id"]
    failed = _wait(client, u["id"], gen_id, "failed")

    assert "simulated ComfyUI failure" in (failed.get("error") or "")
    assert _balance(client, u["id"]) == 100, "a failed generation charged credits"
    assert _charges(client, u["id"], gen_id) == []


def test_timeout_failure_is_not_charged(client, monkeypatch):
    """The specific failure the R9700 produces: the poll budget expiring."""
    class _Slow:
        async def generate(self, **kwargs):
            raise TimeoutError("ComfyUI generation pid-1 timed out after ~300s")

    monkeypatch.setattr(generation_jobs, "get_generator",
                        lambda *a, **k: _Slow())
    u = _user(client, "Timeout Member")
    project = _project(client, u["id"])
    gen_id = _generate(client, u["id"], project["id"]).json()["id"]
    failed = _wait(client, u["id"], gen_id, "failed")

    assert "timed out" in (failed.get("error") or "")
    assert _balance(client, u["id"]) == 100
    assert _charges(client, u["id"], gen_id) == []


def test_successful_generation_is_charged_exactly_once(client):
    u = _user(client, "Image Success Member")
    project = _project(client, u["id"])
    gen_id = _generate(client, u["id"], project["id"]).json()["id"]
    _wait(client, u["id"], gen_id, "completed")

    charges = _charges(client, u["id"], gen_id)
    assert len(charges) == 1, f"expected exactly one charge, got {charges}"
    spent = 100 - _balance(client, u["id"])
    assert spent > 0
    assert abs(charges[0]["amount"]) == spent


def test_completing_twice_does_not_double_charge(client):
    """The guard in _complete_generation, exercised directly.

    A duplicated worker run or a manual re-complete must not take credits
    again; the ledger is keyed on related_id + generation_charge.
    """
    u = _user(client, "Double Charge Member")
    project = _project(client, u["id"])
    gen_id = _generate(client, u["id"], project["id"]).json()["id"]
    _wait(client, u["id"], gen_id, "completed")

    after_first = _balance(client, u["id"])
    assert len(_charges(client, u["id"], gen_id)) == 1

    with SessionLocal() as db:
        gen = db.get(Generation, gen_id)
        assert gen is not None
        generation_jobs._complete_generation(db, gen, gen.file_url or "/storage/x.png")

    assert _balance(client, u["id"]) == after_first, "second completion charged again"
    assert len(_charges(client, u["id"], gen_id)) == 1


def test_insufficient_credits_blocks_before_any_work(client):
    u = _user(client, "Broke Member", credits=0)
    project = _project(client, u["id"])
    resp = _generate(client, u["id"], project["id"])
    assert resp.status_code in (402, 400, 409), resp.text
    assert _balance(client, u["id"]) == 0
