"""Voice library: hear a voice before choosing it, and clone a voice from an audio or video file."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import config
from ..deps import get_current_user
from ..models import User
from ..services import avatar_clone, voice as voice_provider

router = APIRouter(prefix="/api/voice-library", tags=["voice-library"])

_ALLOWED = {".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm", ".mkv", ".m4v"}
_SAMPLE_LINE = "Hello, this is how I sound when I read your script."
_CHUNK = 1024 * 1024
_MAX_MB = 200


def _safe_voice_id(voice_id: str) -> str:
    """Only ids from the real voice list are accepted, so nothing user-typed reaches the file system."""
    if voice_id not in {v["id"] for v in voice_provider.list_voices()}:
        raise HTTPException(status_code=404, detail="Voice not found")
    return voice_id


@router.get("/preview")
def preview(voice_id: str, user: User = Depends(get_current_user)):
    """A short audio sample. Piper voices are synthesised once and cached; a cloned voice plays the
    recording it was cloned from, which is instant and does not load the 7B model."""
    voice_id = _safe_voice_id(voice_id)
    folder = config.STORAGE_DIR / "voice_previews"
    folder.mkdir(parents=True, exist_ok=True)
    if voice_id.startswith(voice_provider.VIBEVOICE_PREFIX):
        name = voice_id[len(voice_provider.VIBEVOICE_PREFIX):]
        target = folder / f"vv_{uuid.uuid5(uuid.NAMESPACE_URL, name).hex}.audio"
        try:
            resp = httpx.get(f"{config.VIBEVOICE_BASE_URL}/api/voices/{name}/preview", timeout=20.0)
            resp.raise_for_status()
            content = resp.content
        except httpx.HTTPError as exc:
            from ..services import voice_studio

            sample = voice_studio.voice_file(name)  # the engine is asleep: play the recording straight from its folder
            if sample is None:
                raise HTTPException(status_code=503, detail="The voice app is not running, so this voice can't be played.") from exc
            content = sample.read_bytes()
        target.write_bytes(content)
        return {"url": f"/storage/voice_previews/{target.name}", "kind": "reference"}
    target = folder / f"piper_{uuid.uuid5(uuid.NAMESPACE_URL, voice_id).hex}.wav"
    if not target.is_file():
        try:
            voice_provider.generate_speech(_SAMPLE_LINE, target, voice_id=voice_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"url": f"/storage/voice_previews/{target.name}", "kind": "synthesised"}


@router.post("/clone", status_code=201)
def clone_voice(
    name: str = Form(min_length=1, max_length=60),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Clone a voice from an audio or video file of the person speaking. The caller must have their consent."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(status_code=400, detail="Upload an MP3, WAV, M4A or a video file.")
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"source{suffix}"
        written = 0
        with source.open("wb") as handle:
            while chunk := file.file.read(_CHUNK):
                written += len(chunk)
                if written > _MAX_MB * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"File is larger than {_MAX_MB} MB.")
                handle.write(chunk)
        sample = Path(tmp) / "voice.wav"
        try:
            avatar_clone.extract_voice_sample(source, sample)
            voice_name = avatar_clone.register_voice(avatar_clone.voice_name_for(name), sample)
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if voice_name is None:
        raise HTTPException(status_code=503, detail="The voice app is not running. Start it and try again.")
    return {"voice_id": f"{voice_provider.VIBEVOICE_PREFIX}{voice_name}", "name": voice_name}


@router.delete("/{name}", status_code=204)
def delete_clone(name: str, user: User = Depends(get_current_user)):
    """Remove a cloned voice from the voice app. Built-in voices cannot be deleted."""
    if f"{voice_provider.VIBEVOICE_PREFIX}{name}" not in {v["id"] for v in voice_provider.list_voices()}:
        raise HTTPException(status_code=404, detail="Cloned voice not found")
    try:
        resp = httpx.delete(f"{config.VIBEVOICE_BASE_URL}/api/voices/{name}", timeout=20.0)
    except httpx.HTTPError as exc:
        from ..services import voice_studio

        if voice_studio.remove_voice_file(name):  # engine asleep: the recording is moved aside in its folder
            return
        raise HTTPException(status_code=503, detail="The voice app is not running.") from exc
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Cloned voice not found")
    resp.raise_for_status()
