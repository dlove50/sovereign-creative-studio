"""Image Templates API: a gallery of one-click recipes over the local image engines.

GET  /api/image-templates                 categories and every template with its fields
POST /api/image-templates/{id}/run        multipart: values (JSON of text/select fields) and one
                                          file part per picture, named after its field id
                                          -> {"kind": "generation", "generation": {...}}
                                          or {"kind": "enhance", "job": {...}}
Results are ordinary generations / enhance jobs: poll /api/generations/{id} or /api/enhance/jobs/{id}.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from ..config import STORAGE_DIR
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import GenerationCreate
from ..services import enhance, image_templates as tpl
from . import generations

router = APIRouter(prefix="/api/image-templates", tags=["image-templates"])

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024


@router.get("")
def catalog(_user: User = Depends(get_current_user)):
    return tpl.catalog()


def _store(upload: UploadFile, folder: Path) -> Path:
    ext = Path(upload.filename or "").suffix.lower()
    if ext not in IMAGE_EXT:
        raise tpl.TemplateError("Pictures must be PNG, JPG or WEBP.")
    data = upload.file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise tpl.TemplateError("A picture is larger than 25 MB.")
    if not data:
        raise tpl.TemplateError("A picture is empty.")
    path = folder / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    return path


def _storage_url(path: Path) -> str:
    return "/storage/" + path.resolve().relative_to(STORAGE_DIR.resolve()).as_posix()


@router.post("/{template_id}/run", status_code=201)
async def run(template_id: str, request: Request, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    try:
        t = tpl.get(template_id)
    except tpl.TemplateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    form = await request.form()
    try:
        values = json.loads(form.get("values") or "{}")
        if not isinstance(values, dict):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="values must be a JSON object.") from exc

    sources = STORAGE_DIR / "image-edit-sources"
    sources.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="template_"))
    try:
        images: dict[str, list[Path]] = {}
        image_fields = {f.id for f in t.fields if f.kind in ("image", "images")}
        for key, item in form.multi_items():
            if key in image_fields and isinstance(item, UploadFile):
                images.setdefault(key, []).append(_store(item, sources))
        clean = tpl.validate(t, values, images)

        if t.engine == "enhance":
            source = images[t.fields[0].id][0]
            job = enhance.create_job(user.id, source, f"{t.name}", list(t.enhance_ops))
            return {"kind": "enhance", "template": t.id, "job": {"id": job["id"], "status": job["status"]}}

        prompt = tpl.build_prompt(t, clean)
        if t.engine == "generate":
            payload = GenerationCreate(prompt=prompt, mode="text_to_image")
        else:
            pictures = tpl.edit_images(t, images, work)
            stored = []
            for p in pictures:
                if p.parent != sources:  # a reference sheet made in the work folder
                    dest = sources / f"{uuid.uuid4().hex}{p.suffix}"
                    shutil.copyfile(p, dest)
                    p = dest
                stored.append(_storage_url(p))
            payload = GenerationCreate(prompt=prompt, mode="image_edit", source_image_url=stored[0],
                                       reference_image_urls=stored[1:])
        gen = generations.create_generation(payload, db, user)
        return {"kind": "generation", "template": t.id,
                "generation": {"id": gen.id, "status": gen.status, "prompt": gen.prompt}}
    except (tpl.TemplateError, enhance.EnhanceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)
