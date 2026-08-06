"""Consent-gated management of Sovereign's local dots.tts voice profiles."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..deps import ADMIN_ROLE, get_current_user
from ..models import User

router = APIRouter(prefix="/api/voice-cloning", tags=["voice-cloning"])
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".mp4", ".mov", ".webm", ".mkv"}
_MAX_BYTES = 50 * 1024 * 1024
_DEFAULT_VOICE_ROOT = Path(
    r"C:\Users\David\Documents\Codex\2026-06-11\codex-what-tool-do-you-use\work\Sovereign-AI-June13"
)


def _profiles_root() -> Path:
    root = Path(os.getenv("SOVEREIGN_VOICE_APP_ROOT", str(_DEFAULT_VOICE_ROOT)))
    return root / "voice_profiles"


def _owner(user: User) -> None:
    if user.role != ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="Owner administrator access is required")


def _profiles() -> list[dict]:
    root = _profiles_root()
    active = ""
    try:
        active = (root / "active.txt").read_text(encoding="utf-8").strip()
    except OSError:
        pass
    items = []
    if root.is_dir():
        for folder in sorted(root.iterdir()):
            if not folder.is_dir() or not _SLUG.fullmatch(folder.name):
                continue
            metadata = {}
            try:
                metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            items.append({
                "slug": folder.name,
                "name": metadata.get("name", folder.name.replace("-", " ").title()),
                "source_type": metadata.get("source_type", "unknown"),
                "configured": (folder / "reference.wav").is_file() and (folder / "reference.txt").is_file(),
                "active": folder.name == active,
            })
    return items


@router.get("/profiles")
def list_profiles(user: User = Depends(get_current_user)):
    _owner(user)
    return {"profiles": _profiles(), "profiles_root": str(_profiles_root())}


@router.post("/profiles", status_code=201)
async def enroll_profile(
    name: str = Form(...),
    transcript: str = Form(...),
    source_type: str = Form("consented-human"),
    rights_confirmed: bool = Form(False),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    _owner(user)
    if not rights_confirmed:
        raise HTTPException(status_code=400, detail="Voice ownership or cloning rights must be confirmed")
    if source_type not in {"consented-human", "synthetic"}:
        raise HTTPException(status_code=400, detail="Invalid source type")
    slug = re.sub(r"[^a-z0-9_-]+", "-", name.strip().lower()).strip("-_")
    if not _SLUG.fullmatch(slug):
        raise HTTPException(status_code=400, detail="Voice name must contain letters or numbers")
    exact_text = transcript.strip()
    if not exact_text:
        raise HTTPException(status_code=400, detail="The exact recording transcript is required")
    if "..." in exact_text or "…" in exact_text:
        raise HTTPException(status_code=400, detail="Reference transcripts cannot omit spoken words with an ellipsis")
    original = Path(file.filename or "sample.wav").name
    suffix = Path(original).suffix.lower()
    if suffix not in _AUDIO_EXTS:
        raise HTTPException(status_code=415, detail="Use WAV, MP3, M4A, AAC, FLAC, OGG, MP4, MOV, WebM, or MKV media")
    content = await file.read(_MAX_BYTES + 1)
    if not content or len(content) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Voice sample must be between 1 byte and 50 MB")
    ffmpeg = shutil.which("ffmpeg") or r"C:\CFFmpeg\ffmpeg\bin\ffmpeg.exe"
    if not Path(ffmpeg).is_file():
        raise HTTPException(status_code=503, detail="FFmpeg is required for voice enrollment")

    profile = _profiles_root() / slug
    profile.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sovereign-voice-") as temp_dir:
        incoming = Path(temp_dir) / f"source{suffix}"
        incoming.write_bytes(content)
        completed = subprocess.run(
            [ffmpeg, "-y", "-i", str(incoming), "-ac", "1", "-ar", "48000", "-sample_fmt", "s16", str(profile / "reference.wav")],
            capture_output=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            raise HTTPException(status_code=422, detail="FFmpeg could not decode the supplied recording")
    (profile / "reference.txt").write_text(exact_text, encoding="utf-8")
    (profile / "metadata.json").write_text(json.dumps({
        "name": name.strip(), "slug": slug, "source_type": source_type,
        "local_only": True, "rights_confirmed": True, "original_filename": original,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2), encoding="utf-8")
    # Enrollment is an explicit selection action: make the newly enrolled
    # profile active so subsequent assistant speech cannot silently remain on
    # an older voice (for example David after enrolling Megatron).
    (_profiles_root() / "active.txt").write_text(slug, encoding="utf-8")
    return next(item for item in _profiles() if item["slug"] == slug)


@router.post("/profiles/{slug}/activate")
def activate_profile(slug: str, user: User = Depends(get_current_user)):
    _owner(user)
    if not _SLUG.fullmatch(slug):
        raise HTTPException(status_code=400, detail="Invalid voice profile")
    profile = _profiles_root() / slug
    if not (profile / "reference.wav").is_file() or not (profile / "reference.txt").is_file():
        raise HTTPException(status_code=404, detail="Configured voice profile not found")
    (_profiles_root() / "active.txt").write_text(slug, encoding="utf-8")
    return {"ok": True, "active": slug}


@router.delete("/profiles/{slug}", status_code=204)
def delete_profile(slug: str, user: User = Depends(get_current_user)):
    _owner(user)
    if not _SLUG.fullmatch(slug):
        raise HTTPException(status_code=400, detail="Invalid voice profile")
    root = _profiles_root()
    profile = root / slug
    if not profile.is_dir():
        raise HTTPException(status_code=404, detail="Voice profile not found")
    shutil.rmtree(profile)
    active_file = root / "active.txt"
    try:
        was_active = active_file.read_text(encoding="utf-8").strip() == slug
    except OSError:
        was_active = False
    if was_active:
        remaining = _profiles()
        if remaining:
            active_file.write_text(remaining[0]["slug"], encoding="utf-8")
        else:
            active_file.unlink(missing_ok=True)
    return Response(status_code=204)


class CloneSynthesisIn(BaseModel):
    profile: str = Field(..., min_length=1, max_length=64)
    text: str = Field(..., min_length=1, max_length=1000)


@router.post("/synthesize")
def synthesize_clone(payload: CloneSynthesisIn, user: User = Depends(get_current_user)):
    """Synthesize through the selected local clone, never Piper/cloud TTS."""
    _owner(user)
    slug = payload.profile.strip().lower()
    if not _SLUG.fullmatch(slug):
        raise HTTPException(status_code=400, detail="Invalid voice profile")
    profile = _profiles_root() / slug
    if not (profile / "reference.wav").is_file() or not (profile / "reference.txt").is_file():
        raise HTTPException(status_code=404, detail="Configured voice profile not found")
    url = os.getenv("SOVEREIGN_DOTS_TTS_URL", "http://127.0.0.1:5555").rstrip("/") + "/api/speech/speak"
    request = urllib.request.Request(
        url,
        data=json.dumps({"text": payload.text.strip(), "profile": slug}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as result:
            audio = result.read()
    except urllib.error.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Local cloning engine rejected synthesis (HTTP {exc.code})") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Local cloning engine is unavailable") from exc
    if not audio:
        raise HTTPException(status_code=502, detail="Local cloning engine returned no audio")
    return Response(content=audio, media_type="audio/wav", headers={"X-Sovereign-TTS": "dots.tts-clone"})
