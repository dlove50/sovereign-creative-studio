"""OpenAI-compatible local image endpoint for OpenDesign.

This deliberately exposes only the small subset OpenDesign needs. Requests are
rendered by the existing ComfyUI adapter and returned as ``b64_json`` so no
public callback URL or cloud storage is required.
"""
from __future__ import annotations

import base64
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import IMAGE_QUALITY_PRESET, STORAGE_DIR
from ..generators.comfyui import ComfyUIGenerator
from ..services import image_presets


router = APIRouter(prefix="/v1/images", tags=["openai-compatible-media"])


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str = "sovereign-flux2-klein"
    n: int = 1
    size: str = "1024x1024"


@router.post("/generations")
async def create_image(payload: ImageGenerationRequest):
    if payload.n != 1:
        raise HTTPException(status_code=400, detail="Local media bridge supports n=1.")

    generation_id = f"open-design-{uuid.uuid4().hex}"
    workflow = image_presets.workflow_for_preset(IMAGE_QUALITY_PRESET)
    generator = ComfyUIGenerator(workflow_path=str(workflow))
    try:
        result = await generator.generate(
            generation_id=generation_id,
            prompt=payload.prompt,
            media_type="image",
        )
        filename = (result.file_url or "").removeprefix("/storage/")
        path = (STORAGE_DIR / filename).resolve()
        path.relative_to(STORAGE_DIR.resolve())
        image_bytes = path.read_bytes()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Local ComfyUI generation failed: {exc}") from exc

    return {
        "created": int(time.time()),
        "data": [{"b64_json": base64.b64encode(image_bytes).decode("ascii")}],
    }

