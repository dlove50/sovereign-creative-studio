"""Voice Studio API: Sovereign's page for VibeVoice (multi-speaker cloned voices, realtime presets, live streaming).

GET    /api/voice-studio/status            engine state (never starts anything)
POST   /api/voice-studio/start             start the engine (loads the chosen or best model in the background)
POST   /api/voice-studio/stop              shut the engine down and free the graphics card
GET    /api/voice-studio/models            installed models and the loaded one
POST   /api/voice-studio/model             switch model (only one fits on the 8 GB card)
GET    /api/voice-studio/voices            recorded voices and realtime preset voices
GET    /api/voice-studio/voices/{name}/audio   preview a voice sample
POST   /api/voice-studio/voices            add a recorded voice sample (wav, mp3, flac, ogg, m4a, aac)
GET    /api/voice-studio/examples          the example scripts
POST   /api/voice-studio/generate          multi-speaker generation (a job)
POST   /api/voice-studio/realtime          single-speaker realtime preset voice (a job)
GET    /api/voice-studio/jobs/{id}         progress; saves the finished clip to the library
GET    /api/voice-studio/jobs/{id}/chunks  live audio so far (16-bit PCM, 24 kHz, base64)
POST   /api/voice-studio/jobs/{id}/stop    stop generating
GET    /api/voice-studio/clips             the clip library (newest first)
GET    /api/voice-studio/clips/{id}/audio  the WAV
DELETE /api/voice-studio/clips/{id}        move a clip to the trash
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User
from ..services import voice_studio as vs

router = APIRouter(prefix="/api/voice-studio", tags=["voice-studio"])
_MAX_UPLOAD = 60 * 1024 * 1024
_scripts: dict[str, str] = {}  # engine job id -> the script, kept so the saved clip carries it


class StartIn(BaseModel):
    model: str | None = Field(default=None, max_length=200)


class ModelIn(BaseModel):
    label: str = Field(max_length=200)


class GenerateIn(BaseModel):
    script: str = Field(min_length=1, max_length=60000)
    num_speakers: int = Field(default=2, ge=1, le=4)
    speakers: list[str] = Field(default_factory=list, max_length=4)
    cfg_scale: float = Field(default=1.3, ge=1.0, le=12.0)
    inference_steps: int = Field(default=5, ge=1, le=50)
    seed: int = Field(default=42, ge=-1)
    disable_voice_cloning: bool = False


class RealtimeIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    voice: str = Field(max_length=100)
    cfg_scale: float = Field(default=1.5, ge=1.0, le=2.0)
    steps: int = Field(default=5, ge=1, le=20)


def _engine(path: str, method: str = "GET", body: dict | None = None, timeout: float = 30.0) -> Any:
    try:
        return vs.call(method, path, body, timeout=timeout)
    except vs.VoiceStudioError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/status")
def status(_user: User = Depends(get_current_user)):
    return vs.engine_status()


@router.post("/start", status_code=202)
def start(body: StartIn | None = None, _user: User = Depends(get_current_user)):
    try:
        return vs.start(body.model if body else None)
    except vs.VoiceStudioError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - say what went wrong instead of a bare "Internal Server Error"
        raise HTTPException(status_code=409, detail=f"The voice engine could not be started: {exc}") from exc


@router.post("/stop")
def stop(_user: User = Depends(get_current_user)):
    return {"stopped": vs.stop()}


@router.get("/models")
def models(_user: User = Depends(get_current_user)):
    return _engine("/models")


@router.post("/model")
def switch_model(body: ModelIn, _user: User = Depends(get_current_user)):
    return _engine("/model", "POST", {"label": body.label}, timeout=600.0)


@router.get("/voices")
def voices(_user: User = Depends(get_current_user)):
    return _engine("/voices")


@router.get("/voices/{name}/audio")
def voice_audio(name: str, _user: User = Depends(get_current_user)):
    import urllib.parse

    try:
        data = vs.fetch_bytes(f"/voices/{urllib.parse.quote(name, safe='')}/audio")
    except vs.VoiceStudioError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    from fastapi.responses import Response

    return Response(content=data, media_type="audio/wav")


@router.post("/voices", status_code=201)
def add_voice(file: UploadFile = File(...), _user: User = Depends(get_current_user)):
    content = file.file.read(_MAX_UPLOAD + 1)
    if not content:
        raise HTTPException(422, "That file is empty.")
    if len(content) > _MAX_UPLOAD:
        raise HTTPException(413, "That recording is too large (60 MB limit).")
    try:
        return vs.upload_voice(file.filename or "voice.wav", content)
    except vs.VoiceStudioError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/examples")
def examples(_user: User = Depends(get_current_user)):
    return _engine("/examples")


@router.post("/generate", status_code=202)
def generate(body: GenerateIn, _user: User = Depends(get_current_user)):
    out = _engine("/generate", "POST", body.model_dump(), timeout=30.0)
    _scripts[out["id"]] = body.script
    return out


@router.post("/realtime", status_code=202)
def realtime(body: RealtimeIn, _user: User = Depends(get_current_user)):
    out = _engine("/realtime", "POST", body.model_dump(), timeout=30.0)
    _scripts[out["id"]] = body.text
    return out


@router.get("/jobs/{job_id}")
def job(job_id: str, _user: User = Depends(get_current_user)):
    state = _engine(f"/jobs/{job_id}")
    if state["status"] == "done" and state.get("has_audio"):
        try:
            clip = vs.save_clip(job_id, state, _scripts.get(job_id))
            state["clip"] = clip
        except vs.VoiceStudioError as exc:
            state["error"] = str(exc)
    return state


@router.get("/jobs/{job_id}/chunks")
def chunks(job_id: str, after: int = 0, _user: User = Depends(get_current_user)):
    return _engine(f"/jobs/{job_id}/chunks?after={max(0, int(after))}")


@router.post("/jobs/{job_id}/stop")
def stop_job(job_id: str, _user: User = Depends(get_current_user)):
    return _engine(f"/jobs/{job_id}/stop", "POST", {})


@router.get("/clips")
def clips(_user: User = Depends(get_current_user)):
    return [{**clip, "audio_url": f"/api/voice-studio/clips/{clip['id']}/audio"} for clip in vs.list_clips()]


@router.get("/clips/{clip_id}/audio")
def clip_audio(clip_id: str, _user: User = Depends(get_current_user)):
    path = vs.clip_audio_path(clip_id)
    if path is None or not path.exists():
        raise HTTPException(404, "Clip not found.")
    return FileResponse(path, media_type="audio/wav", filename=f"voice-studio-{clip_id}.wav")


@router.delete("/clips/{clip_id}", status_code=204)
def delete_clip(clip_id: str, _user: User = Depends(get_current_user)):
    if not vs.delete_clip(clip_id):
        raise HTTPException(404, "Clip not found.")
