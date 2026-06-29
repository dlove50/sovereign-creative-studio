"""Phase 16A: Avatar & Voice foundation — assets, voices, setup-required jobs,
data isolation, and charge-on-success billing."""
import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")
    os.environ["DEFAULT_CREDITS"] = "100"
    os.environ["DEFAULT_SIGNUP_CREDITS"] = "50"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.main import app
from app.models import AvatarJob, CreditTransaction, User
from app.services import avatar_jobs

PNG = b"\x89PNG\r\n\x1a\nfakeimage"
MP4 = b"\x00\x00\x00\x20ftypisomfakevideo"


@pytest.fixture(scope="module", autouse=True)
def _app_ready():
    with TestClient(app):
        yield


def _client():
    return TestClient(app)


def _signup(c, username):
    return c.post("/api/auth/signup", json={"username": username, "password": "avatarpass1", "name": username})


def test_create_photo_avatar():
    c = _client(); _signup(c, "av_photo")
    r = c.post("/api/avatars/photo", data={"name": "My Face"}, files={"file": ("face.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["avatar_type"] == "photo_avatar" and b["status"] == "ready" and b["source_file_path"].endswith(".png")


def test_create_video_avatar():
    c = _client(); _signup(c, "av_video")
    r = c.post("/api/avatars/video", data={"name": "My Clip"}, files={"file": ("clip.mp4", MP4, "video/mp4")})
    assert r.status_code == 201 and r.json()["avatar_type"] == "video_avatar"


def test_bad_extension_rejected():
    c = _client(); _signup(c, "av_badext")
    r = c.post("/api/avatars/photo", files={"file": ("evil.exe", b"x", "application/octet-stream")})
    assert r.status_code == 400


def test_user_lists_only_own_avatars_and_isolation():
    ca = _client(); _signup(ca, "av_a")
    cb = _client(); _signup(cb, "av_b")
    a = ca.post("/api/avatars/photo", data={"name": "A"}, files={"file": ("a.png", PNG, "image/png")}).json()["id"]
    b = cb.post("/api/avatars/photo", data={"name": "B"}, files={"file": ("b.png", PNG, "image/png")}).json()["id"]
    a_ids = {x["id"] for x in ca.get("/api/avatars").json()}
    assert a in a_ids and b not in a_ids
    # B's job id is not visible to A
    assert ca.get(f"/api/avatar-jobs/{b}").status_code == 404


def test_voice_create_and_list():
    c = _client(); _signup(c, "av_voice")
    preset = c.post("/api/voices", json={"name": "Friendly", "voice_type": "preset"}).json()
    assert preset["status"] == "ready"
    local = c.post("/api/voices", json={"name": "Local", "voice_type": "local_tts"}).json()
    assert local["status"] in {"ready", "setup_required"}  # mock backend -> setup_required
    assert any(v["id"] == preset["id"] for v in c.get("/api/voices").json())


def test_greeting_job_setup_required_and_not_charged():
    c = _client(); _signup(c, "av_greet")
    before = c.get("/api/me").json()["credits"]
    r = c.post("/api/avatar-jobs/greeting", json={"script_text": "Hello!"})
    assert r.status_code == 201
    job = r.json()
    assert job["status"] == "setup_required" and job["credits_cost"] == 0
    assert "setup required" in (job["error_message"] or "").lower() or job["error_message"]
    after = c.get("/api/me").json()["credits"]
    assert after == before  # setup-required jobs never charge
    # no avatar_video ledger row for this job
    with SessionLocal() as db:
        charge = db.scalar(
            select(CreditTransaction).where(
                CreditTransaction.related_id == job["id"],
                CreditTransaction.transaction_type == "generation_charge",
            )
        )
    assert charge is None


def test_readiness_reports_setup_required_defaults():
    c = _client(); _signup(c, "av_ready")
    r = c.get("/api/avatars/readiness").json()
    assert r["avatar"]["ready"] is False  # placeholder backend
    assert r["voice"]["ready"] is False  # mock backend
    assert r["greeting_text"] and r["credits_per_avatar_video"] == 15
    assert r["default_avatar_preset"] == "tiny_test"
    assert {p["id"] for p in r["avatar_presets"]} >= {"tiny_test", "low_vram", "balanced", "quality"}
    tiny = next(p for p in r["avatar_presets"] if p["id"] == "tiny_test")
    assert tiny["width"] == 256 and tiny["height"] == 256 and tiny["steps"] == 2 and tiny["cfg"] == 1.0


def test_admin_can_see_all_avatars():
    ca = _client(); _signup(ca, "av_iso_user")
    a = ca.post("/api/avatars/photo", data={"name": "U"}, files={"file": ("u.png", PNG, "image/png")}).json()["id"]
    owner = _client()  # no cookie -> local owner/admin
    all_ids = {x["id"] for x in owner.get("/api/avatars", params={"scope": "all"}).json()}
    assert a in all_ids


def test_voice_greeting_setup_required_charges_zero():
    # Test backend is mock -> not ready -> 409, no charge, no record.
    c = _client(); _signup(c, "voice_mock")
    before = c.get("/api/me").json()["credits"]
    r = c.post("/api/voices/greeting", json={})
    assert r.status_code == 409 and "setup required" in r.json()["detail"].lower()
    assert c.get("/api/me").json()["credits"] == before


def _mock_voice_ready(monkeypatch):
    from app.services import voice as vsvc

    monkeypatch.setattr(vsvc, "voice_readiness", lambda: {"backend": "piper", "ready": True, "detail": "ready"})
    monkeypatch.setattr(vsvc, "model_label", lambda: "en_US-test")

    def fake_gen(text, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfake")

    monkeypatch.setattr(vsvc, "generate_speech", fake_gen)


def test_voice_greeting_success_charges_2_and_in_library(monkeypatch):
    _mock_voice_ready(monkeypatch)
    c = _client(); _signup(c, "voice_ok")
    before = c.get("/api/me").json()["credits"]
    r = c.post("/api/voices/greeting", json={})
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["status"] == "ready" and (v["sample_file_path"] or "").endswith(".wav")
    assert before - c.get("/api/me").json()["credits"] == 2
    with SessionLocal() as db:
        tx = db.scalar(
            select(CreditTransaction).where(
                CreditTransaction.related_id == v["id"],
                CreditTransaction.related_feature == "voice_generation",
            )
        )
    assert tx is not None and tx.amount == -2 and tx.status == "completed"
    assert any(it["id"] == f"voice:{v['id']}" for it in c.get("/api/library").json())


def test_voice_greeting_insufficient_credits_blocks(monkeypatch):
    _mock_voice_ready(monkeypatch)
    c = _client(); _signup(c, "voice_broke")
    me = c.get("/api/me").json()
    with SessionLocal() as db:
        u = db.get(User, me["id"]); u.credits = 1; db.commit()
    r = c.post("/api/voices/greeting", json={})
    assert r.status_code == 402
    assert c.get("/api/me").json()["credits"] == 1  # no charge, no generation


def test_voice_assets_are_user_isolated(monkeypatch):
    _mock_voice_ready(monkeypatch)
    ca = _client(); _signup(ca, "voice_a")
    cb = _client(); _signup(cb, "voice_b")
    va = ca.post("/api/voices/greeting", json={}).json()["id"]
    a_ids = {x["id"] for x in ca.get("/api/voices").json()}
    b_ids = {x["id"] for x in cb.get("/api/voices").json()}
    assert va in a_ids and va not in b_ids


# --- Phase 16C: talking avatar -----------------------------------------------
_FAKE_OBJINFO_READY = {
    "WanInfiniteTalkToVideo": {},
    "AudioEncoderLoader": {"input": {"required": {"audio_encoder_name": [["wav2vec2.safetensors"]]}}},
    "UNETLoader": {"input": {"required": {"unet_name": [["wan2.1_i2v.safetensors"]]}}},
    "ModelPatchLoader": {"input": {"required": {"name": [["infinitetalk.safetensors"]]}}},
    "CLIPLoader": {"input": {"required": {"clip_name": [["umt5_xxl_fp8.safetensors"]]}}},
    "VAELoader": {"input": {"required": {"vae_name": [["wan_2.2_vae.safetensors"]]}}},
}


def test_avatar_readiness_setup_required_when_models_missing(monkeypatch):
    from app import config as cfg
    from app.services import avatar as asvc

    monkeypatch.setattr(cfg, "AVATAR_BACKEND", "comfyui_wan_infinite_talk")
    monkeypatch.setattr(asvc, "_object_info", lambda: {"WanInfiniteTalkToVideo": {}})  # node only, no models
    r = asvc.avatar_readiness()
    assert r["ready"] is False and r["comfy_reachable"] is True and r["node_present"] is True
    assert r["models_present"] is False and len(r["missing"]) >= 1


def test_avatar_readiness_ready_when_mocked(monkeypatch):
    from app import config as cfg
    from app.services import avatar as asvc

    monkeypatch.setattr(cfg, "AVATAR_BACKEND", "comfyui_wan_infinite_talk")
    monkeypatch.setattr(asvc, "_object_info", lambda: _FAKE_OBJINFO_READY)
    monkeypatch.setattr(asvc, "_workflow_path", lambda: __import__("pathlib").Path(__file__))  # any existing file
    monkeypatch.setattr(cfg, "AVATAR_WAN_MODEL_NAME", "wan2.1_i2v.safetensors")
    monkeypatch.setattr(cfg, "AVATAR_INFINITETALK_PATCH_NAME", "infinitetalk.safetensors")
    monkeypatch.setattr(cfg, "AVATAR_AUDIO_ENCODER_NAME", "wav2vec2.safetensors")
    r = asvc.avatar_readiness()
    assert r["ready"] is True and r["missing"] == []


def test_avatar_readiness_accepts_comfy_combo_options_shape(monkeypatch):
    from app import config as cfg
    from app.services import avatar as asvc

    info = {
        "WanInfiniteTalkToVideo": {},
        "AudioEncoderLoader": {
            "input": {"required": {"audio_encoder_name": ["COMBO", {"options": ["chinese-wav2vec2-base.safetensors"]}]}}
        },
        "UNETLoader": {"input": {"required": {"unet_name": [["wan2.1_i2v_480p_14B_fp8_scaled.safetensors"]]}}},
        "ModelPatchLoader": {"input": {"required": {"name": [["infinitetalk_single.safetensors"]]}}},
        "CLIPLoader": {"input": {"required": {"clip_name": [["umt5_xxl_fp8_e4m3fn_scaled.safetensors"]]}}},
        "VAELoader": {"input": {"required": {"vae_name": [["wan_2.1_vae.safetensors"]]}}},
    }
    monkeypatch.setattr(cfg, "AVATAR_BACKEND", "comfyui_wan_infinite_talk")
    monkeypatch.setattr(asvc, "_object_info", lambda: info)
    monkeypatch.setattr(asvc, "_workflow_path", lambda: __import__("pathlib").Path(__file__))
    monkeypatch.setattr(cfg, "AVATAR_WAN_MODEL_NAME", "wan2.1_i2v_480p_14B_fp8_scaled.safetensors")
    monkeypatch.setattr(cfg, "AVATAR_INFINITETALK_PATCH_NAME", "infinitetalk_single.safetensors")
    monkeypatch.setattr(cfg, "AVATAR_AUDIO_ENCODER_NAME", "chinese-wav2vec2-base.safetensors")
    assert asvc.avatar_readiness()["ready"] is True


def _photo_and_voice(c, monkeypatch):
    _mock_voice_ready(monkeypatch)
    avatar_id = c.post("/api/avatars/photo", data={"name": "Me"}, files={"file": ("p.png", PNG, "image/png")}).json()["id"]
    voice_id = c.post("/api/voices/greeting", json={}).json()["id"]
    return avatar_id, voice_id


def test_talking_avatar_setup_required_charges_zero(monkeypatch):
    # Default backend is placeholder -> setup_required, no charge, queued nothing.
    c = _client(); _signup(c, "talk_setup")
    avatar_id, voice_id = _photo_and_voice(c, monkeypatch)
    before = c.get("/api/me").json()["credits"]
    r = c.post("/api/avatar-jobs/talking", json={"avatar_id": avatar_id, "voice_id": voice_id})
    assert r.status_code == 201
    job = r.json()
    assert job["status"] == "setup_required" and job["credits_cost"] == 0
    # voice greeting charged 2, but the talking job itself charges 0
    assert before == c.get("/api/me").json()["credits"]


def _mock_avatar_ready(monkeypatch):
    from app.services import avatar as asvc

    monkeypatch.setattr(
        asvc, "avatar_readiness",
        lambda: {"backend": "comfyui_wan_infinite_talk", "ready": True, "detail": "ready", "missing": []},
    )


def test_talking_avatar_insufficient_credits_blocks(monkeypatch):
    _mock_avatar_ready(monkeypatch)
    c = _client(); _signup(c, "talk_broke")
    avatar_id, voice_id = _photo_and_voice(c, monkeypatch)
    me = c.get("/api/me").json()
    with SessionLocal() as db:
        u = db.get(User, me["id"]); u.credits = 5; db.commit()  # < 15
    r = c.post("/api/avatar-jobs/talking", json={"avatar_id": avatar_id, "voice_id": voice_id})
    assert r.status_code == 402
    assert c.get("/api/me").json()["credits"] == 5  # no charge, nothing queued


def test_talking_avatar_rejects_unknown_preset(monkeypatch):
    _mock_avatar_ready(monkeypatch)
    c = _client(); _signup(c, "talk_bad_preset")
    avatar_id, voice_id = _photo_and_voice(c, monkeypatch)
    r = c.post(
        "/api/avatar-jobs/talking",
        json={"avatar_id": avatar_id, "voice_id": voice_id, "avatar_preset": "raw_1024"},
    )
    assert r.status_code == 422


def test_talking_avatar_cannot_use_other_users_assets(monkeypatch):
    ca = _client(); _signup(ca, "talk_a")
    cb = _client(); _signup(cb, "talk_b")
    a_avatar, a_voice = _photo_and_voice(ca, monkeypatch)
    # B tries to use A's avatar/voice
    r = cb.post("/api/avatar-jobs/talking", json={"avatar_id": a_avatar, "voice_id": a_voice})
    assert r.status_code == 404


def test_talking_avatar_success_saves_mp4_and_charges_15(monkeypatch):
    from app.services import avatar_comfyui as ac

    _mock_avatar_ready(monkeypatch)
    c = _client(); _signup(c, "talk_ok")
    avatar_id, voice_id = _photo_and_voice(c, monkeypatch)
    me = c.get("/api/me").json()
    before = me["credits"]

    async def fake_gen(image_path, audio_path, prompt, out_path, preset=None):
        assert preset.id == "low_vram"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"\x00\x00\x00\x20ftypisomFAKEMP4")

    monkeypatch.setattr(ac, "generate_talking_avatar", fake_gen)

    # create the queued job via the endpoint, then run the worker step synchronously
    job = c.post(
        "/api/avatar-jobs/talking",
        json={"avatar_id": avatar_id, "voice_id": voice_id, "avatar_preset": "low_vram"},
    ).json()
    assert job["status"] == "queued"
    assert job["avatar_preset"] == "low_vram" and job["avatar_width"] == 320
    avatar_jobs._run_avatar_video(job["id"])

    done = c.get(f"/api/avatar-jobs/{job['id']}").json()
    assert done["status"] == "completed" and (done["output_video_path"] or "").endswith(".mp4")
    assert done["avatar_preset"] == "low_vram"
    assert done["avatar_width"] == 320 and done["avatar_steps"] == 4
    assert done["avatar_runtime_seconds"] is not None
    assert before - c.get("/api/me").json()["credits"] == 15
    with SessionLocal() as db:
        tx = db.scalar(
            select(CreditTransaction).where(
                CreditTransaction.related_id == job["id"],
                CreditTransaction.related_feature == "avatar_video",
            )
        )
    assert tx is not None and tx.amount == -15
    assert any(it["id"] == f"avatar_video:{job['id']}" for it in c.get("/api/library").json())


def test_avatar_workflow_patch_applies_preset_values():
    from app.services import avatar_comfyui as ac
    from app.services.avatar_presets import resolve_preset

    workflow = {
        "7": {
            "class_type": "WanInfiniteTalkToVideo",
            "inputs": {
                "width": 1,
                "height": 1,
                "length": 1,
                "start_image": "__SOURCE_IMAGE__",
                "audio_encoder_output_1": "__SOURCE_AUDIO__",
            },
        },
        "8": {"class_type": "KSampler", "inputs": {"steps": 99, "cfg": 9.0}},
        "note": {"_comment": "not executable"},
    }
    patched = ac._patch(workflow, "image.png", "audio.wav", "hello", resolve_preset("balanced"))
    assert patched["7"]["inputs"]["width"] == 384
    assert patched["7"]["inputs"]["height"] == 384
    assert patched["7"]["inputs"]["length"] == 61
    assert patched["7"]["inputs"]["start_image"] == "image.png"
    assert patched["8"]["inputs"]["steps"] == 6
    assert patched["8"]["inputs"]["cfg"] == 1.0


def test_avatar_error_messages_scrub_local_paths():
    msg = avatar_jobs._scrub_paths(r"failed reading C:\Users\David\secret\model.safetensors and /home/x/y/z.onnx")
    assert "C:\\Users" not in msg and "/home/" not in msg and "<path>" in msg


def test_charge_helpers_debit_and_ledger_on_success():
    # Mocked success: the charge helpers debit credits + write a ledger row.
    with SessionLocal() as db:
        u = db.scalars(select(User).where(User.role == "owner_admin")).first()
        start = u.credits
        job = AvatarJob(user_id=u.id, job_type="avatar_greeting", status="completed", provider="comfyui_liveportrait")
        db.add(job); db.commit(); db.refresh(job)
        avatar_jobs.charge_for_avatar_job(db, u, job)
        avatar_jobs.charge_for_voice(db, u, related_id=job.id, provider="piper")
        db.commit()
        rows = db.scalars(
            select(CreditTransaction).where(CreditTransaction.related_id == job.id)
        ).all()
        features = {r.related_feature for r in rows}
        assert "avatar_video" in features and "voice_generation" in features
        assert db.get(User, u.id).credits == start - 15 - 2
