"""Small studio helpers used by the shell and a few tools.

POST /api/assistant/chat            how-to answers and "take me to ..." for the floating studio assistant
GET  /api/developers/endpoints      every route of this backend, read live from its OpenAPI description
POST /api/recordings                save a screen recording from the browser (webm) and make a poster frame
POST /api/slides/document-brief     turn an uploaded PDF / PowerPoint / text file into a short brief for the video tools
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..database import get_db
from ..deps import get_current_user
from ..models import AvatarAsset, User
from ..services import prompt_assist, slides
from ..services.music_playback import find_ffmpeg_tool

router = APIRouter(tags=["studio-extras"])

# ---- Assistant ----------------------------------------------------------------------------------------------------

PAGES = {
    "Home": "/", "Director": "/director", "Music Lab": "/music-lab", "Voice Studio": "/voice-studio",
    "Video agent": "/video-agent", "Avatars": "/avatars", "Voices": "/voices", "Video generator": "/videos",
    "Image studio": "/create", "Scene by scene movies": "/movies", "App library": "/apps", "Credits": "/credits",
    "Projects": "/projects", "Brand": "/brand", "Screen recorder": "/record", "Developer API": "/developers",
    "Motion Studio": "/motion-studio", "Transcribe video": "/video-to-text", "OCR studio": "/ocr-studio",
    "Slides to video": "/slides", "Video podcast": "/podcast", "Translate": "/translate", "Auto clips": "/auto-clips",
    "Inspiration": "/inspiration", "Assets": "/assets-library", "Profile": "/profile", "Status": "/status",
}
_ASSISTANT_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}, "action": {"type": "string", "enum": ["answer", "navigate"]},
                   "page": {"type": "string"}},
    "required": ["reply", "action"],
}


class AssistantTurn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=1500)


class AssistantIn(BaseModel):
    messages: list[AssistantTurn] = Field(min_length=1, max_length=12)


@router.post("/api/assistant/chat")
def assistant_chat(body: AssistantIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    avatars = db.scalar(select(func.count()).select_from(AvatarAsset).where(AvatarAsset.user_id == user.id,
                                                                            AvatarAsset.deleted_at.is_(None))) or 0
    system = (
        "You are the helper inside Sovereign Creative Studio, a local video, music and voice studio. Answer how-to questions "
        "briefly (one to four sentences) and, when the user wants to go somewhere, choose the page. You can only answer and open "
        "pages; you never start a render, spend credits, delete anything or change settings, and you say so if asked to. "
        f"Pages you can open: {', '.join(PAGES)}. The user has {user.credits} credits and {avatars} avatar looks. "
        "Music Lab makes songs, covers and dub plates. Voice Studio turns scripts into speech with several voices and clones "
        "voices from a sample. Director makes whole videos from a template. Reply as JSON with reply, action (answer or navigate) "
        "and page (exactly one of the page names, only when navigating).")
    try:
        response = httpx.post(config.OLLAMA_BASE_URL.rstrip("/") + "/api/chat", timeout=120, json={
            "model": config.PROMPT_ASSIST_MODEL, "stream": False, "think": False, "keep_alive": 0, "format": _ASSISTANT_SCHEMA,
            "options": {"temperature": 0.3, "num_predict": 500},
            "messages": [{"role": "system", "content": system}, *[t.model_dump() for t in body.messages]]})
        response.raise_for_status()
        data = json.loads(response.json()["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="The assistant's model did not answer. Is Ollama running?") from exc
    page = data.get("page") if data.get("action") == "navigate" else None
    page = page if page in PAGES else None
    return {"reply": str(data.get("reply", "")).strip()[:1200] or "Done.", "action": "navigate" if page else "answer",
            "navigate_to": PAGES.get(page) if page else None, "page": page}


# ---- Developer API list -------------------------------------------------------------------------------------------

@router.get("/api/developers/endpoints")
def developer_endpoints(request: Request, _user: User = Depends(get_current_user)):
    spec = request.app.openapi()
    out: list[dict[str, Any]] = []
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            params = op.get("parameters", [])
            content = (op.get("requestBody") or {}).get("content", {})
            body = "multipart" if "multipart/form-data" in content else ("json" if "application/json" in content else None)
            group = (op.get("tags") or [path.split("/")[2] if path.startswith("/api/") and path.count("/") > 1 else "other"])[0]
            description = (op.get("description") or "").strip().splitlines()
            out.append({
                "method": method.upper(), "path": path, "group": group, "summary": op.get("summary", ""),
                "description": description[0] if description else "",
                "path_params": [p["name"] for p in params if p.get("in") == "path"],
                "query_params": [p["name"] for p in params if p.get("in") == "query"], "body": body,
            })
    out.sort(key=lambda e: (e["group"], e["path"], e["method"]))
    return {"count": len(out), "interactive_docs": "/docs", "openapi": "/openapi.json", "endpoints": out}


# ---- Screen recordings -----------------------------------------------------------------------------------------------

MAX_RECORDING_BYTES = 800 * 1024 * 1024


def _probe(path: Path) -> tuple[float, bool]:
    probe = find_ffmpeg_tool("ffprobe")
    if not probe:
        return 0.0, False
    try:
        out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)],
                             capture_output=True, text=True, timeout=60)
        data = json.loads(out.stdout or "{}")
        seconds = float(data.get("format", {}).get("duration") or 0)
        return round(seconds, 1), any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0, False


@router.post("/api/recordings", status_code=201)
def save_recording(file: UploadFile = File(...), title: str = Form(default=""), _user: User = Depends(get_current_user)):
    folder = config.STORAGE_DIR / "recordings"
    folder.mkdir(parents=True, exist_ok=True)
    rec_id = uuid.uuid4().hex[:12]
    target = folder / f"{rec_id}.webm"
    size = 0
    with target.open("wb") as handle:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_RECORDING_BYTES:
                handle.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="That recording is larger than 800 MB.")
            handle.write(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The recording was empty.")
    seconds, has_audio = _probe(target)
    if seconds <= 0:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="That file could not be read as a video.")
    poster = folder / f"{rec_id}.jpg"
    ffmpeg = find_ffmpeg_tool("ffmpeg")
    if ffmpeg:
        subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", f"{min(1.0, seconds / 2):.2f}", "-i", str(target), "-frames:v", "1",
                        "-vf", "scale=640:-2", str(poster)], capture_output=True, timeout=60)
    clean_title = re.sub(r"\s+", " ", title).strip()[:120] or "Screen recording"
    return {"id": rec_id, "title": clean_title, "result_url": f"/storage/recordings/{target.name}",
            "poster_url": f"/storage/recordings/{poster.name}" if poster.exists() else "",
            "duration_seconds": seconds, "has_audio": has_audio}


# ---- Document brief ---------------------------------------------------------------------------------------------------

BRIEF_SUFFIXES = {".pdf", ".pptx", ".txt", ".md"}
BRIEF_MAX_MB = 50
BRIEF_SOURCE_CHARS = 30000
BRIEF_TARGET_CHARS = 3500


@router.post("/api/slides/document-brief")
def document_brief(file: UploadFile = File(...), _user: User = Depends(get_current_user)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in BRIEF_SUFFIXES:
        raise HTTPException(status_code=400, detail="Upload a PDF, PowerPoint, .txt or .md file.")
    data = file.file.read(BRIEF_MAX_MB * 1024 * 1024 + 1)
    if len(data) > BRIEF_MAX_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is larger than {BRIEF_MAX_MB} MB.")
    if suffix in {".txt", ".md"}:
        text = " ".join(data.decode("utf-8", errors="replace").split())
    else:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / f"doc{suffix}"
            source.write_bytes(data)
            try:
                text = " ".join(slides.extract_slides(source))
            except RuntimeError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not text.strip():
        raise HTTPException(status_code=422, detail="No readable text was found in that file (scanned pages are not read yet).")
    source_chars = len(text)
    condensed = source_chars > BRIEF_TARGET_CHARS
    brief = text
    if condensed:
        try:
            brief = prompt_assist.condense(text[:BRIEF_SOURCE_CHARS], BRIEF_TARGET_CHARS)
        except prompt_assist.PromptAssistError:
            brief = text[:BRIEF_TARGET_CHARS]
    suggested = max(2, min(10, round(len(brief) / 450)))
    return {"name": Path(file.filename or "file").name, "brief": brief, "source_chars": source_chars,
            "condensed": condensed, "ocr_pages": 0, "suggested_slides": suggested}
