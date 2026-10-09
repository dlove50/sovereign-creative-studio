"""Dub plate studio API (waveform, cues, preview and final render).

GET  /api/music/songs/{id}/dub               waveform peaks, BPM, beat grid, saved cues and loops
PUT  /api/music/songs/{id}/dub/state         save cues, loops and the beat grid
POST /api/music/songs/{id}/dub/preview       render the cut to a preview file
GET  /api/music/songs/{id}/dub/preview/audio the preview MP3
POST /api/music/songs/{id}/dub/render        press the dub plate (vocal side, version side or both) into the library
POST /api/music/songs/{id}/dub/special       make a sung special with YuE2 (a job; its vocal is isolated)
POST /api/music/songs/{id}/stems             split a song into vocal and instrumental (Demucs)
GET  /api/music/songs/{id}/stems/{name}      the isolated vocals or instrumental (WAV)
GET  /api/music/dub/voices                   installed voices for the voice "special"
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User
from ..services import dubplate, music, stems, voice

router = APIRouter(prefix="/api/music", tags=["music-dub"])


class CueIn(BaseModel):
    slot: int = Field(ge=0, lt=dubplate.MAX_CUES)
    time: float = Field(ge=0)
    label: str = Field(default="", max_length=24)


class LoopIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    label: str = Field(default="", max_length=24)


class StateIn(BaseModel):
    cues: list[CueIn] = Field(default_factory=list, max_length=dubplate.MAX_CUES)
    loops: list[LoopIn] = Field(default_factory=list, max_length=dubplate.MAX_LOOPS)
    bpm: float = Field(default=0, ge=0, le=300)
    beat_offset: float = Field(default=0, ge=0)


class SpecialIn(BaseModel):
    text: str = Field(min_length=1, max_length=dubplate.MAX_SPECIAL_CHARS)
    sound_name: str = Field(default="", max_length=60)


class DropIn(BaseModel):
    at: float = Field(ge=0)
    beats: float = Field(default=4, ge=0.25, le=32)


class RenderIn(BaseModel):
    start: float = Field(default=0, ge=0)
    end: float | None = Field(default=None, ge=0)
    tempo_pct: float = Field(default=0, ge=-16, le=16)
    pitch: float = Field(default=0, ge=-6, le=6)
    eq_low: float = Field(default=0, ge=-12, le=12)
    eq_mid: float = Field(default=0, ge=-12, le=12)
    eq_high: float = Field(default=0, ge=-12, le=12)
    filter_mode: str = "off"
    filter_hz: float = Field(default=1000, ge=40, le=16000)
    echo: bool = False
    echo_division: str = "1/4"
    echo_feedback: float = Field(default=0.45, ge=0, le=0.85)
    echo_mix: float = Field(default=0.4, ge=0, le=1)
    reverb: float = Field(default=0, ge=0, le=1)
    drops: list[DropIn] = Field(default_factory=list, max_length=dubplate.MAX_DROPS)
    fade_in: float = Field(default=0, ge=0, le=20)
    fade_out: float = Field(default=2, ge=0, le=30)
    master: bool = True
    special_text: str = Field(default="", max_length=dubplate.MAX_SPECIAL_CHARS)
    special_placement: str = "none"
    special_voice: str | None = Field(default=None, max_length=80)
    special_mode: str = "spoken"
    special_song_id: str | None = Field(default=None, max_length=12)
    sides: str = "vocal"
    special_volume: float = Field(default=1.0, ge=0.3, le=2.0)
    sound_name: str = Field(default="", max_length=60)
    title: str = Field(default="", max_length=80)


def _song_or_404(song_id: str) -> dict:
    try:
        song = music.get_song(song_id)
    except music.MusicError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found.")
    return song


def _bad_request(exc: music.MusicError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/songs/{song_id}/dub")
def get_dub(song_id: str, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        return {**dubplate.analyze(song_id), "state": dubplate.get_state(song_id),
                "has_stems": stems.has_stems(song_id), "stems_available": stems.stems_available()}
    except music.MusicError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/songs/{song_id}/dub/state")
def put_state(song_id: str, body: StateIn, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        return dubplate.save_state(song_id, body.model_dump())
    except music.MusicError as exc:
        raise _bad_request(exc) from exc


@router.post("/songs/{song_id}/dub/preview")
def preview(song_id: str, body: RenderIn, side: str = "vocal", _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        path = dubplate.render_preview(song_id, body.model_dump(), side)
    except music.MusicError as exc:
        raise _bad_request(exc) from exc
    return {"audio_url": f"/api/music/songs/{song_id}/dub/preview/audio?v={int(path.stat().st_mtime)}"}


@router.get("/songs/{song_id}/dub/preview/audio")
def preview_audio(song_id: str, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    path = dubplate.preview_path(song_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="No preview rendered yet.")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@router.post("/songs/{song_id}/dub/render", status_code=201)
def render(song_id: str, body: RenderIn, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        made = dubplate.render_dubplate(song_id, body.model_dump())
    except music.MusicError as exc:
        raise _bad_request(exc) from exc
    return {"songs": [{**song, "audio_url": f"/api/music/songs/{song['id']}/audio"} for song in made]}


@router.post("/songs/{song_id}/dub/special", status_code=202)
def make_special(song_id: str, body: SpecialIn, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        return dubplate.make_sung_special(song_id, body.text, body.sound_name)
    except music.MusicError as exc:
        raise _bad_request(exc) from exc


@router.post("/songs/{song_id}/stems")
def split_stems(song_id: str, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        stems.ensure_stems(song_id)
    except music.MusicError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"has_stems": True}


@router.get("/songs/{song_id}/stems/{name}")
def stem_audio(song_id: str, name: str, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        path = stems.stem_path(song_id, name)
    except music.MusicError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="This song has not been split yet.")
    return FileResponse(path, media_type="audio/wav")


@router.get("/dub/voices")
def voices(_user: User = Depends(get_current_user)):
    return {"ready": voice.voice_ready(),
            "voices": [{"id": v["id"], "label": v["label"], "is_default": v.get("is_default", False)}
                       for v in voice.list_voices() if v.get("ready", True)]}
