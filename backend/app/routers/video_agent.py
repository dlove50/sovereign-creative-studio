"""Video agent API: write a spoken script from a plain-language request."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User
from ..services import video_agent

router = APIRouter(prefix="/api/video-agent", tags=["video-agent"])


class ScriptIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=8000)
    seconds: int = Field(default=30, ge=10, le=180)


class ScriptOut(BaseModel):
    title: str
    script: str
    model: str
    target_words: int


@router.post("/script", response_model=ScriptOut)
def write_script(payload: ScriptIn, user: User = Depends(get_current_user)):
    """Runs local Qwen (no credits). Sync def: FastAPI runs it in a worker thread."""
    try:
        return video_agent.write_script(payload.prompt, payload.seconds)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
