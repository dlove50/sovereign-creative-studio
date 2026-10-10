"""Prompt assist API: clean up a spoken or typed prompt, or write the whole thing from an idea.

POST /api/prompt-assist/clean  {text, kind, context}      -> {text}
POST /api/prompt-assist/write  {idea, kind, context}      -> {text}
POST /api/prompt-assist/movie  {idea, seconds, context}   -> {plan, text}   (bible + titled chapters)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User
from ..services import prompt_assist as pa

router = APIRouter(prefix="/api/prompt-assist", tags=["prompt-assist"])


class CleanIn(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    kind: str = Field(default="general", max_length=20)
    context: str = Field(default="", max_length=300)


class WriteIn(BaseModel):
    idea: str = Field(min_length=1, max_length=4000)
    kind: str = Field(default="general", max_length=20)
    context: str = Field(default="", max_length=300)


class MovieIn(BaseModel):
    idea: str = Field(min_length=1, max_length=4000)
    seconds: int = Field(default=60, ge=10, le=600)
    context: str = Field(default="", max_length=300)


def _run(fn, *args):
    try:
        return fn(*args)
    except pa.PromptAssistError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/clean")
def clean(body: CleanIn, _user: User = Depends(get_current_user)):
    return {"text": _run(pa.clean, body.text, body.kind, body.context)}


@router.post("/write")
def write(body: WriteIn, _user: User = Depends(get_current_user)):
    return {"text": _run(pa.write, body.idea, body.kind, body.context)}


@router.post("/movie")
def movie(body: MovieIn, _user: User = Depends(get_current_user)):
    return _run(pa.write_movie, body.idea, body.seconds, body.context)
