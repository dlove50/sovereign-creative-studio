"""Music Lab API: local song generation with YuE2.

GET    /api/music/status             engine + provider availability
POST   /api/music/engine/start       start the dedicated music engine
POST   /api/music/generate           queue a song, returns a job
GET    /api/music/jobs/{id}          job progress / result
GET    /api/music/songs              song library (newest first)
GET    /api/music/songs/{id}         one song
GET    /api/music/songs/{id}/audio   the MP3 (range requests supported)
GET    /api/music/songs/{id}/viz     real waveform/spectrum data for the display
POST   /api/music/create             describe a song in one line; lyrics are written automatically
POST   /api/music/lyrics-chat        one turn of a songwriting chat (returns the full current lyrics)
POST   /api/music/cover              re-make a library song in a new style (a job)
POST   /api/music/play/{id}          play a song through the speakers
POST   /api/music/pause              pause the speakers
POST   /api/music/resume             resume from the same spot
POST   /api/music/seek               jump to a position (seconds)
POST   /api/music/stop               stop playback
GET    /api/music/now-playing        what is playing right now (and how far in)
PATCH  /api/music/songs/{id}         rename / favorite
DELETE /api/music/songs/{id}
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User
from ..services import music, music_compose, music_cover, music_playback

router = APIRouter(prefix="/api/music", tags=["music"])


class GenerateIn(BaseModel):
    title: str | None = Field(default=None, max_length=80)
    style: str = Field(min_length=1, max_length=music.MAX_STYLE_CHARS)
    lyrics: str | None = Field(default=None, max_length=music.MAX_LYRICS_CHARS)
    instrumental: bool = False
    duration: float = Field(default=60.0, ge=music.MIN_SECONDS, le=music.MAX_SECONDS)
    seed: int | None = Field(default=None, ge=0)
    quality: str = "V0"
    auto_play: bool = False


class CreateIn(BaseModel):
    idea: str = Field(min_length=1, max_length=600)
    genre: str | None = Field(default=None, max_length=60)
    instrumental: bool = False
    duration: float = Field(default=60.0, ge=music.MIN_SECONDS, le=music.MAX_SECONDS)
    seed: int | None = Field(default=None, ge=0)
    quality: str = "V0"
    auto_play: bool = True


class CoverIn(BaseModel):
    song_id: str = Field(min_length=12, max_length=12)
    style: str = Field(min_length=1, max_length=music.MAX_STYLE_CHARS)
    lyrics: str | None = Field(default=None, max_length=music.MAX_LYRICS_CHARS)
    title: str | None = Field(default=None, max_length=80)
    auto_play: bool = False


class ChatTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=3000)


class CurrentSong(BaseModel):
    title: str = Field(default="", max_length=80)
    style: str = Field(default="", max_length=music.MAX_STYLE_CHARS)
    lyrics: str = Field(default="", max_length=music.MAX_LYRICS_CHARS)


class LyricsChatIn(BaseModel):
    messages: list[ChatTurn] = Field(min_length=1, max_length=40)
    current: CurrentSong | None = None


class SongPatch(BaseModel):
    title: str | None = Field(default=None, max_length=80)
    favorite: bool | None = None


def _song_or_404(song_id: str) -> dict:
    try:
        song = music.get_song(song_id)
    except music.MusicError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found.")
    return song


def _with_urls(song: dict) -> dict:
    return {**song, "audio_url": f"/api/music/songs/{song['id']}/audio"}


@router.get("/status")
def get_status(_user: User = Depends(get_current_user)):
    engine = music.engine_status()
    return {
        "default_provider": "yue2",
        "providers": [
            {"id": "yue2", "label": "YuE2 (local, free)", "available": engine["ready"], "detail": engine["detail"]},
            {"id": "elevenlabs", "label": "ElevenLabs (paid cloud)", "available": True,
             "detail": "Opens Cloud Studio music mode; uses ElevenLabs credits."},
        ],
        "engine": engine,
        "limits": {
            "min_seconds": music.MIN_SECONDS, "max_seconds": music.MAX_SECONDS,
            "max_lyrics_chars": music.MAX_LYRICS_CHARS, "max_style_chars": music.MAX_STYLE_CHARS,
            "qualities": list(music.QUALITIES),
            "typical_minutes_per_song_minute": music.TYPICAL_MIN_PER_SONG_MIN,
            "slow_minutes_per_song_minute": music.SLOW_MIN_PER_SONG_MIN,
        },
    }


@router.post("/engine/start")
def start_engine(_user: User = Depends(get_current_user)):
    try:
        return music.start_engine()
    except music.MusicError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/generate", status_code=202)
def generate(body: GenerateIn, _user: User = Depends(get_current_user)):
    try:
        params = music.normalize_request(
            title=body.title, style=body.style, lyrics=body.lyrics, instrumental=body.instrumental,
            duration=body.duration, seed=body.seed, quality=body.quality)
        params["auto_play"] = body.auto_play
    except music.MusicError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return music.create_job(params)


@router.post("/create", status_code=202)
def create_from_idea(body: CreateIn, _user: User = Depends(get_current_user)):
    """One call: write the lyrics, compose the song with YuE2, save it and (optionally) play it."""
    try:
        params = music.normalize_idea(
            idea=body.idea, genre=body.genre, instrumental=body.instrumental, duration=body.duration,
            seed=body.seed, quality=body.quality, auto_play=body.auto_play)
    except music.MusicError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return music.create_job(params)


@router.post("/lyrics-chat")
def lyrics_chat(payload: LyricsChatIn, user: User = Depends(get_current_user)):
    try:
        return music_compose.chat_lyrics(
            [turn.model_dump() for turn in payload.messages], payload.current.model_dump() if payload.current else None)
    except music.MusicError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/cover", status_code=202)
def cover(body: CoverIn, _user: User = Depends(get_current_user)):
    """Re-make a library song in a new style, keeping its melody and lyrics."""
    _song_or_404(body.song_id)
    try:
        return music_cover.create_cover_job(body.song_id, body.style, body.lyrics, body.title, body.auto_play)
    except music.MusicError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/play/{song_id}")
def play(song_id: str, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        state = music_playback.play_song(song_id)
    except music.MusicError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if state["song"]:
        state["song"] = _with_urls(state["song"])
    return state


def _with_song_urls(state: dict) -> dict:
    if state["song"]:
        state["song"] = _with_urls(state["song"])
    return state


@router.post("/pause")
def pause(_user: User = Depends(get_current_user)):
    return _with_song_urls(music_playback.pause_playback())


@router.post("/resume")
def resume(_user: User = Depends(get_current_user)):
    try:
        return _with_song_urls(music_playback.resume_playback())
    except music.MusicError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class SeekIn(BaseModel):
    position: float = Field(ge=0, le=36000)


@router.post("/seek")
def seek(body: SeekIn, _user: User = Depends(get_current_user)):
    try:
        return _with_song_urls(music_playback.seek_playback(body.position))
    except music.MusicError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop")
def stop(_user: User = Depends(get_current_user)):
    return music_playback.stop_playback()


@router.get("/now-playing")
def now_playing(_user: User = Depends(get_current_user)):
    state = music_playback.now_playing()
    if state["song"]:
        state["song"] = _with_urls(state["song"])
    return state


@router.get("/songs/{song_id}/viz")
def song_viz(song_id: str, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        return music_playback.visual_data(song_id)
    except music.MusicError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(job_id: str, _user: User = Depends(get_current_user)):
    job = music.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.get("song_id"):
        song = music.get_song(job["song_id"])
        if song:
            job["song"] = _with_urls(song)
    return job


@router.get("/songs")
def list_songs(_user: User = Depends(get_current_user)):
    return [_with_urls(s) for s in music.list_songs()]


@router.get("/songs/{song_id}")
def get_song(song_id: str, _user: User = Depends(get_current_user)):
    return _with_urls(_song_or_404(song_id))


@router.get("/songs/{song_id}/audio")
def get_audio(song_id: str, _user: User = Depends(get_current_user)):
    song = _song_or_404(song_id)
    return FileResponse(music.audio_path(song["id"]), media_type="audio/mpeg", filename=f"{song['title']}.mp3")


@router.patch("/songs/{song_id}")
def patch_song(song_id: str, body: SongPatch, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    updated = music.update_song(song_id, title=body.title, favorite=body.favorite)
    return _with_urls(updated)


@router.delete("/songs/{song_id}", status_code=204)
def delete_song(song_id: str, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    music.delete_song(song_id)
