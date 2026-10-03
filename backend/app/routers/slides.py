"""Slides to video API: upload a PDF/PPTX, get back a draft scene-by-scene video."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Movie, User
from ..services import movies, slides

router = APIRouter(prefix="/api/slides", tags=["slides"])
_CHUNK = 1024 * 1024
_MAX_MB = 50


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
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if len(pages) > slides.MAX_SLIDES:
        pages = pages[: slides.MAX_SLIDES]
        cap_note = [f"Only the first {slides.MAX_SLIDES} slides were used."]
    else:
        cap_note = []
    scripts, warnings = slides.build_scripts(pages, narrate=rewrite)
    if not scripts:
        raise HTTPException(status_code=422, detail="No readable text was found. Scanned slides need OCR first.")
    scenes = [
        movies.clean_scene({"avatar_id": avatar_id, "tts_voice_id": tts_voice_id or None, "script": s})
        for s in scripts
    ]
    title = Path(file.filename or "Slides").stem[:200] or "Slides"
    movie = Movie(user_id=user.id, title=title, orientation=orientation)
    movies.save_scenes(movie, scenes)
    db.add(movie)
    db.commit()
    return {"movie_id": movie.id, "scenes": len(scenes), "warnings": cap_note + warnings,
            "credits_estimate": movies.cost_estimate(scenes)}
