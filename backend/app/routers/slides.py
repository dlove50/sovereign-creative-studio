"""Slides to video API: upload a PDF/PPTX, get back a draft scene-by-scene video."""
from __future__ import annotations

import tempfile
import uuid
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from .. import config
from ..database import get_db
from ..deps import get_current_user
from ..models import AvatarAsset, Movie, User, Project
from ..services import movies, slides, slide_visuals, brand_spec

router = APIRouter(prefix="/api/slides", tags=["slides"])
_CHUNK = 1024 * 1024
_MAX_MB = 50


class PresentationIn(BaseModel):
    prompt: str = Field(min_length=10, max_length=8000)
    slide_count: int = Field(default=4, ge=2, le=10)
    avatar_id: str = Field(max_length=32)
    tts_voice_id: str = Field(default="", max_length=200)
    orientation: Literal["portrait", "landscape"] = "landscape"
    brand_project_id: str | None = Field(default=None, max_length=32)


@router.post("/generate", status_code=201)
def generate_presentation(payload: PresentationIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from ..services import presentation
    if len(payload.prompt.strip()) < 10:
        raise HTTPException(422, "Describe the presentation in at least 10 characters.")
    avatar = db.get(AvatarAsset, payload.avatar_id)
    if avatar is None or avatar.user_id != user.id or avatar.deleted_at is not None or not avatar.source_file_path:
        raise HTTPException(404, "Choose one of your avatar looks.")
    visuals, logo = {}, None
    if payload.brand_project_id:
        project = db.get(Project, payload.brand_project_id)
        if project is None or project.user_id != user.id:
            raise HTTPException(404, "Brand system not found.")
        visuals = brand_spec.load_spec(project.brand_spec_json)
        for item in visuals["logos"]:
            prefix = f"/api/projects/{project.id}/brand-assets/"
            name = item["url"].removeprefix(prefix)
            if item["url"].startswith(prefix) and re.fullmatch(r"[a-f0-9]{32}\.png", name):
                candidate = config.STORAGE_DIR / "brand" / project.id / name
                if candidate.is_file():
                    logo = candidate
                    break
    images = []
    try:
        deck = presentation.draft(payload.prompt, payload.slide_count)
        movie = Movie(id=uuid.uuid4().hex, user_id=user.id, title=deck.title, orientation=payload.orientation)
        images = presentation.render(deck, config.STORAGE_DIR / "movie_slides" / movie.id, visuals, logo)
        scenes = [movies.clean_scene({"avatar_id": payload.avatar_id, "tts_voice_id": payload.tts_voice_id or None,
            "script": slide.narration, "slide_image_url": f"/api/movies/{movie.id}/slides/{image.name}"})
            for slide, image in zip(deck.slides, images)]
        movies.save_scenes(movie, scenes)
        db.add(movie)
        db.commit()
    except Exception as exc:
        db.rollback()
        for image in images:
            image.unlink(missing_ok=True)
        if isinstance(exc, RuntimeError):
            raise HTTPException(422, str(exc)) from exc
        raise
    return {"movie_id": movie.id, "scenes": len(scenes), "warnings": ["Review generated facts and narration before rendering. Slide visuals are static images."],
            "credits_estimate": movies.cost_estimate(scenes)}


@router.post("/to-movie", status_code=201)
def slides_to_movie(
    file: UploadFile = File(...),
    avatar_id: str = Form(...),
    tts_voice_id: str = Form(default=""),
    orientation: Literal["portrait", "landscape"] = Form(default="landscape"),
    rewrite: bool = Form(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Creates a draft only (no credits). Sync def so the Qwen rewrite runs in a worker thread."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".pptx"}:
        raise HTTPException(status_code=400, detail="Upload a PDF or a .pptx PowerPoint file.")
    avatar = db.get(AvatarAsset, avatar_id)
    if avatar is None or avatar.user_id != user.id or avatar.deleted_at is not None or not avatar.source_file_path:
        raise HTTPException(404, "Choose one of your avatar looks.")
    movie = Movie(id=uuid.uuid4().hex, user_id=user.id,
                  title=Path(file.filename or "Slides").stem[:200] or "Slides", orientation=orientation)
    images = []
    warnings = []
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"deck{suffix}"
        written = 0
        with source.open("wb") as handle:
            while chunk := file.file.read(_CHUNK):
                written += len(chunk)
                if written > _MAX_MB * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"File is larger than {_MAX_MB} MB.")
                handle.write(chunk)
        try:
            pages = slides.extract_slides(source)
            if len(pages) > slides.MAX_SLIDES:
                pages = pages[:slides.MAX_SLIDES]
                warnings.append(f"Only the first {slides.MAX_SLIDES} slides were used.")
            if suffix == ".pdf":
                images = slide_visuals.page_images(source, config.STORAGE_DIR / "movie_slides" / movie.id, len(pages))
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        scenes = []
        if images:
            for index, text in enumerate(pages):
                if text.strip():
                    scripts, notes = slides.build_scripts([text], narrate=rewrite)
                    warnings.extend(note.replace("Slide 1", f"Slide {index + 1}") for note in notes)
                    script = scripts[0] if scripts else ""
                else:
                    script = ""
                    warnings.append(f"Slide {index + 1} has no readable text. Its image was retained; add narration in the editor.")
                scenes.append(movies.clean_scene({"avatar_id": avatar_id, "tts_voice_id": tts_voice_id or None,
                    "script": script, "slide_image_url": f"/api/movies/{movie.id}/slides/{images[index].name}"}))
        else:
            scripts, notes = slides.build_scripts(pages, narrate=rewrite)
            warnings.extend(notes)
            if not scripts:
                raise HTTPException(422, "No readable text was found. Export scanned slides to PDF to retain their images.")
            warnings.append("PowerPoint text was imported. Export the deck to PDF and import that file to preserve its slide visuals.")
            scenes = [movies.clean_scene({"avatar_id": avatar_id, "tts_voice_id": tts_voice_id or None, "script": s}) for s in scripts]
        movies.save_scenes(movie, scenes)
        db.add(movie)
        db.commit()
    except Exception:
        db.rollback()
        for image in images:
            image.unlink(missing_ok=True)
        raise
    return {"movie_id": movie.id, "scenes": len(scenes), "warnings": warnings,
            "credits_estimate": movies.cost_estimate(scenes)}


_KNOWLEDGE_SUFFIXES = {".pdf", ".pptx", ".txt", ".md"}
_KNOWLEDGE_CHARS = 5000


@router.post("/extract-text")
def extract_text(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Plain text from a PDF, PowerPoint, .txt or .md file, so the video agent can write from it."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _KNOWLEDGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Upload a PDF, PowerPoint, .txt or .md file.")
    data = file.file.read(_MAX_MB * 1024 * 1024 + 1)
    if len(data) > _MAX_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is larger than {_MAX_MB} MB.")
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
        raise HTTPException(status_code=422, detail="No readable text was found in that file.")
    return {"name": Path(file.filename or "file").name, "text": text[:_KNOWLEDGE_CHARS], "truncated": len(text) > _KNOWLEDGE_CHARS}
