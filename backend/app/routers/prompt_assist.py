"""Prompt helper API: clean up dictated text, write a piece from an idea, plan a short film.

POST /api/prompt-assist/clean   {text, kind, context} -> {text}
POST /api/prompt-assist/write   {idea, kind, context} -> {text}
POST /api/prompt-assist/movie   {idea, seconds, context} -> {plan, text}
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_current_user
from ..models import User
from ..services import prompt_assist

router = APIRouter(prefix="/api/prompt-assist", tags=["prompt-assist"])


class CleanIn(BaseModel):
    text: str = Field(min_length=1, max_length=prompt_assist.MAX_TEXT)
    kind: str = Field(default="general", max_length=20)
    context: str = Field(default="", max_length=prompt_assist.MAX_CONTEXT)


class WriteIn(BaseModel):
    idea: str = Field(min_length=1, max_length=prompt_assist.MAX_TEXT)
    kind: str = Field(default="general", max_length=20)
    context: str = Field(default="", max_length=prompt_assist.MAX_CONTEXT)


class MovieIn(BaseModel):
    idea: str = Field(min_length=1, max_length=prompt_assist.MAX_TEXT)
    seconds: int = Field(default=60, ge=10, le=600)
    context: str = Field(default="", max_length=prompt_assist.MAX_CONTEXT)


def _call(fn, *args):
    try:
        return fn(*args)
    except prompt_assist.PromptAssistError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/clean")
def clean(body: CleanIn, _user: User = Depends(get_current_user)):
    return {"text": _call(prompt_assist.clean, body.text, body.kind, body.context)}


@router.post("/write")
def write(body: WriteIn, _user: User = Depends(get_current_user)):
    return {"text": _call(prompt_assist.write, body.idea, body.kind, body.context)}


@router.post("/movie")
def movie(body: MovieIn, _user: User = Depends(get_current_user)):
    return _call(prompt_assist.movie, body.idea, body.seconds, body.context)
