"""Music Lab import API: your own songs, their isolated vocal and their timed lyrics.

POST /api/music/import                        upload one or more audio files into the library
GET  /api/music/songs/{id}/vocals             vocal waveform once the song is split (has_stems False before)
POST /api/music/songs/{id}/transcribe         split the vocal and write down the timed lyrics (a job)
GET  /api/music/lyrics-jobs/{job_id}          that job's progress
PUT  /api/music/songs/{id}/lyric-lines        save corrected lyric lines (timing kept)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..database import get_db
from ..models import User, Project
from ..services import music, music_import

router = APIRouter(prefix="/api/music", tags=["music"])


class LyricLine(BaseModel):
    start: float
    end: float
    text: str = Field(default="", max_length=music_import.MAX_LINE_CHARS)


class LyricLinesIn(BaseModel):
    lines: list[LyricLine] = Field(max_length=music_import.MAX_LINES)


def _with_urls(song: dict) -> dict:
    return {**song, "audio_url": f"/api/music/songs/{song['id']}/audio"}


def _song_or_404(song_id: str) -> None:
    try:
        found = music.get_song(song_id)
    except music.MusicError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if found is None:
        raise HTTPException(status_code=404, detail="Song not found.")


@router.post("/import")
def import_songs(files: list[UploadFile] = File(...), project_id: str | None = Form(default=None),
                 db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    if project_id:
        project = db.get(Project, project_id)
        if project is None or project.user_id != _user.id:
            raise HTTPException(status_code=404, detail="Project not found")
    songs, errors = [], []
    for upload in files:
        data = upload.file.read(music_import.MAX_IMPORT_BYTES + 1)
        try:
            songs.append(_with_urls(music_import.import_song(upload.filename or "", data, user_id=_user.id, project_id=project_id)))
        except music.MusicError as exc:
            errors.append({"filename": upload.filename, "error": str(exc)})
    return {"songs": songs, "errors": errors}


@router.get("/songs/{song_id}/vocals")
def vocals(song_id: str, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        return music_import.vocal_waveform(song_id)
    except music.MusicError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/songs/{song_id}/transcribe", status_code=202)
def transcribe(song_id: str, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    return music_import.start_transcription(song_id)


@router.get("/lyrics-jobs/{job_id}")
def lyrics_job(job_id: str, _user: User = Depends(get_current_user)):
    job = music_import.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {**job, "song": _with_urls(job["song"]) if job.get("song") else None}


@router.put("/songs/{song_id}/lyric-lines")
def put_lyric_lines(song_id: str, body: LyricLinesIn, _user: User = Depends(get_current_user)):
    _song_or_404(song_id)
    try:
        song = music_import.save_lyric_lines(song_id, [line.model_dump() for line in body.lines])
    except music.MusicError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _with_urls(song)
