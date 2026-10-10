"""Prompt assist: tidy a spoken or typed prompt, or write the whole thing from a one-line idea.

Runs on the local writing model (the same one the songwriting chat uses, kept loaded between calls). Every kind of prompt
box in the studio uses the same two calls:
  clean  - fix grammar, drop filler and repetition, organise it; keep every idea, add nothing
  write  - turn a bare idea into the finished text for that box (lyrics, a podcast script, an image prompt ...)
Movies get the TECHNIQUE of David's reference film (docs/examples/escape-from-the-wild-script.md), never its story: a
bible (look, cast with identity and wardrobe locks, rules, sound) and titled chapters with beats, camera cues and guards.
"""
from __future__ import annotations

import json
from typing import Any

from .. import config
from .music import MusicError, clean_text
from .music_compose import _ollama_chat


class PromptAssistError(Exception):
    pass


KINDS = ("general", "movie", "story", "lyrics", "song_idea", "podcast", "narration", "visual", "video", "style")

_WRITE_GUIDE = {
    "general": "Write a clear, complete, well-organised version of what the user wants, ready to use as-is.",
    "story": "Write a vivid story premise of 4 to 6 sentences: who the characters are, where it happens, what goes wrong, "
             "how it escalates and how it ends. Original characters and places only.",
    "lyrics": "Write complete ORIGINAL song lyrics from start to end with section tags on their own lines ([verse], [chorus], "
              "[bridge], [outro]). Never copy or paraphrase an existing song.",
    "song_idea": "Write a two to three sentence description of the song: what it is about, the mood, the genre and the voice.",
    "podcast": "Write a complete conversation script. Every line starts with 'Speaker 1:' or 'Speaker 2:' (up to 'Speaker 4:'). "
               "Natural spoken language, a clear opening, a middle that develops the topic, and a closing.",
    "narration": "Write a complete spoken narration script in short, natural sentences, ready to be read aloud.",
    "visual": "Write one detailed image prompt: subject, setting, composition, lighting, lens and mood, as a single paragraph. "
              "No text in the image unless asked.",
    "video": "Write one detailed video shot prompt: subject and action, setting, camera movement, lighting and mood, as a single "
             "paragraph describing a few seconds of footage.",
    "style": "Write a short comma-separated list of style tags: genre, mood, tempo, instruments and vocal type. No artist names.",
}

_CLEAN_SYSTEM = (
    "You turn what someone said or typed into a clean, well-organised request. It may be a rambling voice transcript. "
    "Fix grammar and spelling, remove filler words, false starts and repetition, and organise the ideas in a sensible order. "
    "Keep EVERY idea, name, number and detail the person gave. Do not add new facts, characters or requirements. "
    "Instructions about the result (for example 'make it happy' or 'keep it short') stay instructions about the result. "
    "Keep it about the same length or shorter, in the same language. Reply only with JSON containing text."
)

TEXT_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

MOVIE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "logline": {"type": "string"},
        "look": {"type": "string"},
        "cast": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "identity": {"type": "string"}, "wardrobe": {"type": "string"}},
            "required": ["name", "identity", "wardrobe"]}},
        "rules": {"type": "string"},
        "sound": {"type": "string"},
        "chapters": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "seconds": {"type": "integer"}, "beats": {"type": "string"},
            "guards": {"type": "string"}}, "required": ["title", "seconds", "beats", "guards"]}},
    },
    "required": ["title", "logline", "look", "cast", "rules", "sound", "chapters"],
}

_MOVIE_SYSTEM = (
    "You are a film writer. Turn the user's idea into a complete short film plan in the structure of a professional "
    "AI-video script. Reply only with JSON:\n"
    "- title: a short film title.\n- logline: one sentence.\n"
    "- look: the visual look and format that suits THIS idea (genre, realism, colour, aspect ratio), for example 'Warm cinematic drama, 16:9'.\n"
    "- cast: every recurring character with name, identity (age, build, face, hair, skin tone) and wardrobe (exact clothes "
    "and accessories); these never change between chapters.\n"
    "- rules: global rules for every shot, for example 'Natural action and anatomy, coherent camera cuts, no text on screen'.\n"
    "- sound: the sound or music bed.\n"
    "- chapters: {count} titled chapters that tell the whole story from start to end with rising stakes and an ending that "
    "pays off the opening. Each chapter has a punchy title, seconds (3 to 15), beats (what happens in order, with camera cues "
    "such as 'Cut to', 'Close-up of', 'End with') and guards (what must or must not happen, to keep continuity).\n"
    "The chapter seconds must add up to about {seconds} seconds. Start beats with the action itself, not with 'Cut to'. "
    "If the user is in the story ('me', 'my wife', 'my son'), they and their family are the main characters: use the names "
    "they give, otherwise call them '[You]', '[Your wife]' and so on so they can rename them, and leave identity as "
    "'from your reference photo'. Otherwise invent original characters; never real celebrities, brands or franchises."
)


def _ask(system: str, user: str, schema: dict, timeout: float = 600.0) -> dict[str, Any]:
    try:
        raw = _ollama_chat([{"role": "system", "content": system}, {"role": "user", "content": user}], schema,
                           timeout=timeout, model=config.MUSIC_CHAT_MODEL, keep_alive="10m", num_ctx=8192)
    except MusicError as exc:
        raise PromptAssistError(str(exc).replace("lyric writer", "writing model")) from exc
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise PromptAssistError("The writing model returned something unusable. Try again.") from exc


def clean(text: str, kind: str = "general", context: str = "") -> str:
    text = clean_text(text)
    if not text:
        raise PromptAssistError("There is nothing to clean up yet.")
    hint = f"\nThis is for: {context}." if context else ""
    if kind == "lyrics":
        hint += "\nThese are song lyrics: keep the section tags and line breaks."
    if kind == "podcast":
        hint += "\nThis is a conversation script: keep every 'Speaker N:' label and the line breaks."
    out = clean_text(str(_ask(_CLEAN_SYSTEM + hint, text, TEXT_SCHEMA).get("text", "")))
    if not out:
        raise PromptAssistError("The writing model returned nothing. Try again.")
    return out


def write(idea: str, kind: str = "general", context: str = "") -> str:
    idea = clean_text(idea)
    if not idea:
        raise PromptAssistError("Say or type an idea first.")
    if kind not in _WRITE_GUIDE:
        kind = "general"
    system = ("You are a professional writer for a creative studio. " + _WRITE_GUIDE[kind]
              + (f" It is for: {context}." if context else "") + " Reply only with JSON containing text.")
    out = clean_text(str(_ask(system, f"Idea: {idea}", TEXT_SCHEMA).get("text", "")))
    if not out:
        raise PromptAssistError("The writing model returned nothing. Try again.")
    return out


def format_movie(plan: dict[str, Any]) -> str:
    """The plan as an editable script (the same layout as the reference film)."""
    lines = [plan["title"].upper(), plan["logline"], "", "BIBLE (repeated for every scene)", f"Look: {plan['look']}"]
    for person in plan["cast"]:
        lines.append(f"{person['name']}: {person['identity']}. Wardrobe: {person['wardrobe']}.")
    lines += [f"Rules: {plan['rules']}", f"Sound: {plan['sound']}", "", "CHAPTERS"]
    for i, chapter in enumerate(plan["chapters"], start=1):
        lines.append(f"{i}. {chapter['title']} ({chapter['seconds']} s)")
        lines.append(f"   {chapter['beats']}")
        if chapter.get("guards"):
            lines.append(f"   Keep: {chapter['guards']}")
    return "\n".join(lines)


def write_movie(idea: str, seconds: int = 60, context: str = "") -> dict[str, Any]:
    idea = clean_text(idea)
    if not idea:
        raise PromptAssistError("Say or type an idea first.")
    seconds = max(10, min(600, int(seconds)))
    count = max(3, min(12, round(seconds / 15)))
    system = _MOVIE_SYSTEM.format(count=count, seconds=seconds) + (f"\nVideo format: {context}." if context else "")
    plan = _ask(system, f"Idea: {idea}", MOVIE_SCHEMA)
    chapters = [c for c in plan.get("chapters") or [] if clean_text(c.get("title")) and clean_text(c.get("beats"))]
    if len(chapters) < 2 or not plan.get("cast"):
        raise PromptAssistError("The writing model did not produce a usable script. Try again.")
    for chapter in chapters:
        chapter["seconds"] = max(3, min(15, int(chapter.get("seconds") or 5)))
        chapter["guards"] = clean_text(chapter.get("guards"))
    plan = {**plan, "chapters": chapters}
    return {"plan": plan, "text": format_movie(plan)}
