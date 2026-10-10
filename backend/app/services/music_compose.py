"""Music Lab songwriting: turn a one-line idea into a title, style tags and ORIGINAL lyrics.

A small local model (``MUSIC_LYRICS_MODEL``) writes the words, then is unloaded
immediately (``keep_alive: 0``) so the GPU is free for the YuE2 engine.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .. import config
from .music import MAX_LYRICS_CHARS, MAX_STYLE_CHARS, MusicError, clean_text

GENRE_HINTS = (
    "reggae", "dancehall", "dub", "ska", "rock", "pop", "folk", "country", "blues", "jazz", "hip hop",
    "rap", "r&b", "soul", "funk", "disco", "house", "techno", "edm", "lofi", "metal", "punk", "gospel",
    "latin", "salsa", "bossa nova", "afrobeat", "soca", "classical", "ambient", "synthwave",
)

SONG_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}, "style": {"type": "string"}, "lyrics": {"type": "string"}},
    "required": ["title", "style", "lyrics"],
}


def _ollama_chat(messages: list[dict], schema: dict, timeout: float = 240.0) -> str:
    payload = {
        "model": config.MUSIC_LYRICS_MODEL, "messages": messages, "stream": False, "think": False,
        "format": schema, "keep_alive": 0, "options": {"temperature": 0.9},
    }
    req = urllib.request.Request(
        config.OLLAMA_BASE_URL.rstrip("/") + "/api/chat", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)["message"]["content"]
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        raise MusicError(f"The lyric writer ({config.MUSIC_LYRICS_MODEL}) is not available: {exc}") from exc


def detect_genre(text: str) -> str | None:
    lowered = text.lower()
    return next((g for g in GENRE_HINTS if g in lowered), None)


def compose_song(idea: str, genre: str | None = None, duration: float = 60.0, language: str = "English") -> dict[str, str]:
    """Return {"title", "style", "lyrics"} for a one-line idea such as "a reggae song about my dog"."""
    idea = clean_text(idea)
    if not idea:
        raise MusicError("Tell me what the song should be about.")
    genre = clean_text(genre) or detect_genre(idea) or "pop"
    lines = max(8, min(64, int(duration // 4)))
    system = (
        "You are a professional songwriter. Write ORIGINAL song lyrics from the user's idea. "
        "Never copy or paraphrase the lyrics of any existing song. Put section tags on their own line, "
        "such as [verse], [chorus], [bridge], [outro]. Keep lines singable and of similar length. "
        f"Write about {lines} lines in {language}. The style field is a short comma-separated tag list "
        "describing genre, mood, tempo, instruments and vocal type, with no artist names. "
        "Reply only with JSON containing title, style and lyrics.")
    user = f"Idea: {idea}\nGenre: {genre}"
    raw = _ollama_chat([{"role": "system", "content": system}, {"role": "user", "content": user}], SONG_SCHEMA)
    try:
        data = json.loads(raw)
        title, style, lyrics = clean_text(data["title"]), clean_text(data["style"]), clean_text(data["lyrics"])
    except (ValueError, KeyError, TypeError) as exc:
        raise MusicError("The lyric writer returned something unusable. Try again.") from exc
    if len(lyrics.splitlines()) < 4:
        raise MusicError("The lyric writer produced too little text. Try again.")
    if genre.lower() not in style.lower():
        style = f"{genre}, {style}" if style else genre
    if not re.search(r"^\s*\[[^\]]+\]", lyrics, re.M):
        lyrics = "[verse]\n" + lyrics
    return {
        "title": title[:80] or idea[:60].title(),
        "style": style[:MAX_STYLE_CHARS],
        "lyrics": lyrics[:MAX_LYRICS_CHARS],
    }


CHAT_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}, "title": {"type": "string"}, "style": {"type": "string"}, "lyrics": {"type": "string"}},
    "required": ["reply", "title", "style", "lyrics"],
}
MAX_CHAT_TURNS = 24


def lyrics_chat(messages: list[dict], current: dict | None = None, duration: float = 120.0) -> dict[str, str]:
    """One turn of a songwriting chat. Returns the writer's short reply and the full updated song."""
    turns = [{"role": m["role"], "content": clean_text(m["content"])[:2000]} for m in messages[-MAX_CHAT_TURNS:]
             if m.get("role") in ("user", "assistant") and clean_text(m.get("content", ""))]
    if not turns or turns[-1]["role"] != "user":
        raise MusicError("Say what the song should be about.")
    lines = max(8, min(64, int(duration // 4)))
    system = (
        "You are a friendly professional songwriter working with the user on ONE song. Write ORIGINAL lyrics only and never "
        "copy or paraphrase an existing song. Every reply must contain the COMPLETE updated song: title, style (a short "
        "comma-separated tag list for genre, mood, tempo, instruments and vocal type, no artist names) and lyrics with section "
        f"tags such as [verse], [chorus], [bridge] on their own lines, about {lines} lines. Apply the user's latest request to "
        "the current song and keep everything they did not ask to change. 'reply' is one or two short sentences saying what "
        "you did; never put the lyrics in the reply. Reply only with JSON.")
    if current and clean_text(current.get("lyrics", "")):
        system += (f"\n\nCurrent song\nTitle: {clean_text(current.get('title', ''))}\nStyle: {clean_text(current.get('style', ''))}\n"
                   f"Lyrics:\n{clean_text(current['lyrics'])[:MAX_LYRICS_CHARS]}")
    raw = _ollama_chat([{"role": "system", "content": system}, *turns], CHAT_SCHEMA)
    try:
        data = json.loads(raw)
        reply = clean_text(data["reply"])
        title, style, lyrics = clean_text(data["title"]), clean_text(data["style"]), clean_text(data["lyrics"])
    except (ValueError, KeyError, TypeError) as exc:
        raise MusicError("The lyric writer returned something unusable. Try again.") from exc
    if len(lyrics.splitlines()) < 4:
        raise MusicError("The lyric writer produced too little text. Try again.")
    if not re.search(r"^\s*\[[^\]]+\]", lyrics, re.M):
        lyrics = "[verse]\n" + lyrics
    return {"reply": reply[:400] or "Updated the song.", "title": title[:80], "style": style[:MAX_STYLE_CHARS],
            "lyrics": lyrics[:MAX_LYRICS_CHARS]}
