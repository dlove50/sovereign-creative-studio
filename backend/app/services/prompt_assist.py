"""Prompt helpers: tidy what someone said, or write the whole thing from an idea, with the local writing model.

Used under the text boxes in Voice Studio, Music Lab, the Director and the video tools. Nothing here sends text
anywhere except the local Ollama server.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .. import config

KINDS = {"general", "story", "lyrics", "song_idea", "podcast", "narration", "visual", "video", "style", "movie"}
MAX_TEXT = 8000
MAX_CONTEXT = 1500
TIMEOUT = 240.0

_FORMAT = {
    "general": "plain, clear prose",
    "story": "a short story with a clear beginning, middle and end, in plain prose",
    "lyrics": "song lyrics with section tags on their own lines such as [verse], [chorus], [bridge], [outro]; original words only",
    "song_idea": "one or two sentences describing a song: its subject, mood, genre and who sings it",
    "podcast": ('a spoken script where every line starts with "Speaker 1:", "Speaker 2:" (and so on) followed by what that person '
                "says. Natural, conversational, no stage directions, no markdown"),
    "narration": "narration to be read aloud by one voice: flowing sentences, no headings, no stage directions",
    "visual": "one vivid image prompt: subject, setting, light, camera framing and style, in a single paragraph",
    "video": "one video prompt: the subject, the action in order, the camera movement, the light and the sound, in a single paragraph",
    "style": "a short comma-separated list of style tags (genre, mood, tempo, instruments, vocal type)",
}

_CLEAN_RULES = (
    "You tidy text that was typed or dictated. Fix grammar, spelling and punctuation, remove filler words and accidental "
    "repeats, and organise it so it reads well. Keep every idea, name, number and instruction the person gave; add nothing "
    "new and do not change the meaning. Return only the cleaned text, with no preface and no quotation marks."
)
_WRITE_RULES = (
    "You are a skilled writer. Turn the person's idea into a complete, ready-to-use piece in the requested format. Use their "
    "names, places and facts exactly. Write original words only; never reproduce another work. Return only the finished text, "
    "with no preface, no title unless the format needs one, and no commentary."
)


class PromptAssistError(RuntimeError):
    pass


def _model() -> str:
    return config.PROMPT_ASSIST_MODEL


def _chat(system: str, user: str, *, schema: dict | None = None, temperature: float = 0.6, num_predict: int = 2500) -> str:
    body: dict[str, Any] = {
        "model": _model(), "stream": False, "think": False, "keep_alive": 0,
        "options": {"temperature": temperature, "num_predict": num_predict},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    if schema is not None:
        body["format"] = schema
    try:
        response = httpx.post(config.OLLAMA_BASE_URL.rstrip("/") + "/api/chat", json=body, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise PromptAssistError("The writing model did not answer. Is Ollama running?") from exc
    if response.status_code == 404:
        raise PromptAssistError(f"The writing model '{_model()}' is not installed. Run: ollama pull {_model()}")
    if response.status_code >= 400:
        raise PromptAssistError(f"The writing model failed (HTTP {response.status_code}).")
    try:
        return response.json()["message"]["content"].strip()
    except (KeyError, ValueError) as exc:
        raise PromptAssistError("The writing model returned nothing usable.") from exc


def _tidy(text: str) -> str:
    text = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", text.strip())
    text = re.sub(r"^(here(?:'s| is)[^\n:]*:)\s*\n", "", text, flags=re.I)
    return text.strip().strip('"').strip()


def _check(kind: str, text: str, limit: int = MAX_TEXT) -> tuple[str, str]:
    kind = kind if kind in KINDS else "general"
    text = (text or "").strip()
    if not text:
        raise PromptAssistError("Type or say something first.")
    if len(text) > limit:
        raise PromptAssistError(f"That is too long for the helper (limit {limit} characters).")
    return kind, text


def clean(text: str, kind: str, context: str = "") -> str:
    kind, text = _check(kind, text)
    fmt = _FORMAT.get(kind, _FORMAT["general"])
    note = f"\nThe result should stay in this format: {fmt}." if kind in ("podcast", "lyrics", "style") else ""
    ctx = f"\nBackground: {context[:MAX_CONTEXT]}" if context.strip() else ""
    return _tidy(_chat(_CLEAN_RULES + note + ctx, text, temperature=0.2))


def write(idea: str, kind: str, context: str = "") -> str:
    kind, idea = _check(kind, idea)
    fmt = _FORMAT.get(kind, _FORMAT["general"])
    ctx = f"\nBackground: {context[:MAX_CONTEXT]}" if context.strip() else ""
    system = f"{_WRITE_RULES}\nFormat: {fmt}.{ctx}"
    return _tidy(_chat(system, f"The idea:\n{idea}", temperature=0.8, num_predict=3000))


_MOVIE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"}, "logline": {"type": "string"}, "look": {"type": "string"},
        "cast": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "identity": {"type": "string"}, "wardrobe": {"type": "string"}},
            "required": ["name", "identity", "wardrobe"]}},
        "rules": {"type": "string"}, "sound": {"type": "string"},
        "chapters": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "seconds": {"type": "integer"}, "beats": {"type": "string"}, "guards": {"type": "string"}},
            "required": ["title", "seconds", "beats", "guards"]}},
    },
    "required": ["title", "logline", "look", "cast", "rules", "sound", "chapters"],
}


def movie(idea: str, seconds: int, context: str = "") -> dict[str, Any]:
    _, idea = _check("movie", idea)
    seconds = max(10, min(int(seconds or 60), 600))
    chapters = max(1, min(8, round(seconds / 10)))
    ctx = f"\nBackground: {context[:MAX_CONTEXT]}" if context.strip() else ""
    system = (
        "You plan a short film from an idea so a video model can make it consistently. Give the film a title and a one sentence "
        "logline, one 'look' paragraph (palette, lighting, camera style), the cast (each with a fixed identity description and "
        "fixed wardrobe so they look the same in every chapter), plain 'rules' that must hold in every shot (no on-screen text, "
        "no extra people, and so on), a 'sound' note, and exactly "
        f"{chapters} chapters whose 'seconds' add up to {seconds}. Each chapter has 'beats' (what visibly happens, in order) and "
        "'guards' (what must not change from the previous chapter). Use original characters and places only." + ctx)
    raw = _chat(system, f"The idea:\n{idea}", schema=_MOVIE_SCHEMA, temperature=0.6, num_predict=3500)
    try:
        plan = json.loads(raw)
    except ValueError as exc:
        raise PromptAssistError("The writing model did not return a usable plan. Try again.") from exc
    plan["chapters"] = [c for c in plan.get("chapters", []) if c.get("beats")]
    if not plan["chapters"]:
        raise PromptAssistError("The plan came back empty. Try again with a little more detail.")
    total = sum(max(1, int(c.get("seconds") or 1)) for c in plan["chapters"])
    scale = seconds / total if total else 1.0
    for c in plan["chapters"]:
        c["seconds"] = max(2, round(int(c.get("seconds") or 1) * scale))
    return {"plan": plan, "text": movie_text(plan)}


def movie_text(plan: dict[str, Any]) -> str:
    cast = "\n".join(f"- {c['name']}: {c['identity']}. Wardrobe: {c['wardrobe']}." for c in plan.get("cast", []))
    chapters = "\n".join(
        f"Chapter {i}: {c['title']} ({c['seconds']} seconds). {c['beats']} Keep consistent: {c['guards']}"
        for i, c in enumerate(plan["chapters"], start=1))
    return (f"{plan['title']}. {plan['logline']}\n\nLook: {plan['look']}\n\nCast:\n{cast}\n\nRules: {plan['rules']}\n"
            f"Sound: {plan['sound']}\n\n{chapters}").strip()


def condense(text: str, target_chars: int = 3500) -> str:
    """Shorten a long document into a brief that keeps its facts, names and numbers."""
    system = (
        "You condense documents. Write a faithful brief of the document that keeps every important fact, name, number and "
        f"the order of ideas, in about {target_chars} characters. Use plain paragraphs and short lists where helpful. "
        "Never invent facts. Return only the brief.")
    return _tidy(_chat(system, text, temperature=0.2, num_predict=1800))
