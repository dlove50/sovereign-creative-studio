"""Voice Studio API: VibeVoice text-to-speech and voice cloning inside Sovereign.

GET    /api/voice-studio/status                 engine state (installed, online, ready, loading, model)
POST   /api/voice-studio/start                  start the voice engine (optionally with a model)
POST   /api/voice-studio/stop                   stop it
GET    /api/voice-studio/models                 downloaded models
POST   /api/voice-studio/model                  switch model
GET    /api/voice-studio/voices                 preset and cloned voices
GET    /api/voice-studio/voices/{name}/audio    preview a voice
POST   /api/voice-studio/voices                 clone a voice from an audio sample
DELETE /api/voice-studio/voices/{name}          remove a cloned voice
GET    /api/voice-studio/examples               example scripts
POST   /api/voice-studio/generate               render a conversation / podcast
POST   /api/voice-studio/realtime               real-time speech (needs the Realtime model)
GET    /api/voice-studio/jobs/{id}              progress
GET    /api/voice-studio/jobs/{id}/chunks       live audio chunks (empty for the full models)
POST   /api/voice-studio/jobs/{id}/stop         cancel a queued render
GET    /api/voice-studio/clips                  finished clips
GET    /api/voice-studio/clips/{id}/audio       a clip's WAV
DELETE /api/voice-studio/clips/{id}             delete a clip
"""
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User
from ..services import voice_studio

router = APIRouter(prefix="/api/voice-studio", tags=["voice-studio"])


class StartIn(BaseModel):
    model: str | None = Field(default=None, max_length=64)


class ModelIn(BaseModel):
    label: str = Field(min_length=1, max_length=64)


class GenerateIn(BaseModel):
    script: str = Field(min_length=1, max_length=120_000)
    num_speakers: int = Field(default=2, ge=1, le=4)
    speakers: list[str] = Field(default_factory=list, max_length=4)
    cfg_scale: float = Field(default=1.3, ge=1.0, le=3.0)
    inference_steps: int = Field(default=10, ge=3, le=100)
    seed: int = Field(default=-1, ge=-1, le=2**31 - 1)
    disable_voice_cloning: bool = False


class RealtimeIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    voice: str = Field(default="", max_length=64)
    cfg_scale: float = Field(default=1.5, ge=1.0, le=3.0)
    steps: int = Field(default=5, ge=1, le=50)


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except voice_studio.VoiceStudioError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/status")
def get_status(_user: User = Depends(get_current_user)):
    return voice_studio.status()


@router.post("/start")
def start(body: StartIn, _user: User = Depends(get_current_user)):
    return _call(voice_studio.start, body.model)


@router.post("/stop")
def stop(_user: User = Depends(get_current_user)):
    return _call(voice_studio.stop)


@router.get("/models")
def models(_user: User = Depends(get_current_user)):
    return _call(voice_studio.models)


@router.post("/model")
def switch_model(body: ModelIn, _user: User = Depends(get_current_user)):
    return _call(voice_studio.switch_model, body.label)


@router.get("/voices")
def voices(_user: User = Depends(get_current_user)):
    return _call(voice_studio.voices)


@router.get("/voices/{name}/audio")
def voice_audio(name: str, _user: User = Depends(get_current_user)):
    return Response(_call(voice_studio.voice_audio, name), media_type="audio/wav")


@router.post("/voices", status_code=201)
async def add_voice(file: UploadFile = File(...), _user: User = Depends(get_current_user)):
    data = await file.read()
    return _call(voice_studio.add_voice, file.filename or "voice", data)


@router.delete("/voices/{name}")
def delete_voice(name: str, _user: User = Depends(get_current_user)):
    return _call(voice_studio.delete_voice, name)


@router.get("/examples")
def examples(_user: User = Depends(get_current_user)):
    return _call(voice_studio.examples)


@router.post("/generate", status_code=202)
def generate(body: GenerateIn, _user: User = Depends(get_current_user)):
    return _call(voice_studio.generate, body.script, body.num_speakers, body.speakers, body.cfg_scale,
                 body.inference_steps, body.seed, body.disable_voice_cloning)


@router.post("/realtime", status_code=202)
def realtime(body: RealtimeIn, _user: User = Depends(get_current_user)):
    return _call(voice_studio.realtime, body.text, body.voice, body.cfg_scale, body.steps)


@router.get("/jobs/{job_id}")
def job(job_id: str, _user: User = Depends(get_current_user)):
    return _call(voice_studio.job, job_id)


@router.get("/jobs/{job_id}/chunks")
def chunks(job_id: str, after: int = 0, _user: User = Depends(get_current_user)):
    return _call(voice_studio.chunks, job_id, max(0, after))


@router.post("/jobs/{job_id}/stop")
def stop_job(job_id: str, _user: User = Depends(get_current_user)):
    return _call(voice_studio.stop_job, job_id)


@router.get("/clips")
def clips(_user: User = Depends(get_current_user)):
    return voice_studio.clips()


@router.get("/clips/{clip_id}/audio")
def clip_audio(clip_id: str, _user: User = Depends(get_current_user)):
    return FileResponse(_call(voice_studio.clip_audio_path, clip_id), media_type="audio/wav")


@router.delete("/clips/{clip_id}", status_code=204)
def delete_clip(clip_id: str, _user: User = Depends(get_current_user)):
    if not _call(voice_studio.delete_clip, clip_id):
        raise HTTPException(status_code=404, detail="Clip not found.")
