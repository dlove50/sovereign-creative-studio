"""OCR Studio API: read text from a page image with the local RapidOCR engine (CPU, no download)."""
from __future__ import annotations

import base64
import io

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User
from ..services import ocr

router = APIRouter(prefix="/api/ocr", tags=["ocr"])
_MAX_BYTES = 25 * 1024 * 1024


class ReadIn(BaseModel):
    image: str = Field(min_length=32, max_length=40_000_000, description="A data URL or base64 string of a PNG, JPEG or WEBP page.")


@router.get("/status")
def status(user: User = Depends(get_current_user)):
    return {"available": ocr.available(), "engine": "RapidOCR (local, CPU)"}


@router.post("/read")
def read_page(payload: ReadIn, user: User = Depends(get_current_user)):
    if not ocr.available():
        raise HTTPException(503, "The local OCR engine is not installed.")
    data = payload.image.split(",", 1)[1] if payload.image.startswith("data:") else payload.image
    try:
        raw = base64.b64decode(data, validate=False)
    except Exception:
        raise HTTPException(422, "That image could not be decoded.")
    if len(raw) > _MAX_BYTES:
        raise HTTPException(413, "That page image is too large (25 MB limit).")
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception:
        raise HTTPException(422, "That file is not a readable image.")
    return {"text": ocr.read_image(image)}
