"""Covers: re-make a library song in a new style, keeping its melody and lyrics.

The engine's SheetSage node reads the song's melody into a score, and YuE2 then
performs that score in the new style ("melody" mode, which is what YuE2 recommends
for covers). Only songs already in the Music Lab library can be covered.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .. import config
from . import music
from .music import MusicError, audio_path, clean_text, get_song
from .music_playback import audio_duration

AUDIO_ENCODER = "sheetsage2_bf16.safetensors"


def build_cover_workflow(
    *, style: str, lyrics: str, duration: float, seed: int, quality: str, audio_name: str, filename_prefix: str,
) -> dict[str, Any]:
    """Same pipeline as text-to-music, but the score comes from the reference audio instead of the ABC writer."""
    workflow = music.build_workflow(
        style=style, lyrics=lyrics, duration=duration, seed=seed, quality=quality, mode="melody",
        filename_prefix=filename_prefix)
    del workflow["2"]  # no generated score: the reference song supplies it
    workflow["9"] = {"class_type": "LoadAudio", "inputs": {"audio": audio_name}}
    workflow["10"] = {"class_type": "AudioEncoderLoader", "inputs": {"audio_encoder_name": AUDIO_ENCODER}}
    workflow["11"] = {"class_type": "SheetSage2AudioToABC", "inputs": {
        "audio_encoder": ["10", 0], "audio": ["9", 0], "mode": "melody"}}
    workflow["3"]["inputs"]["abc"] = ["11", 0]
    return workflow


def create_cover_job(song_id: str, style: str, lyrics: str | None = None, title: str | None = None,
                     auto_play: bool = False) -> dict[str, Any]:
    source = get_song(song_id)
    if source is None:
        raise MusicError("Song not found.")
    style = clean_text(style)
    if not style:
        raise MusicError("Say what style the cover should be in (for example: jazz-funk, warm, saxophone).")
    duration = audio_duration(audio_path(song_id)) or float(source.get("duration_requested") or 60)
    duration = float(max(music.MIN_SECONDS, min(music.MAX_SECONDS, duration)))
    instrumental = bool(source.get("instrumental"))
    params = music.normalize_request(
        title=clean_text(title) or f"{source['title']} (Cover)"[:80], style=style,
        lyrics=clean_text(lyrics) or source.get("lyrics") or "", instrumental=instrumental,
        duration=duration, seed=int(time.time() * 1000) % (2**31), quality="V0")
    staged: dict[str, Path] = {}

    def build(job_id: str, p: dict[str, Any]) -> dict[str, Any]:
        input_dir = Path(config.MUSIC_COMFYUI_DIR) / "input"
        if not input_dir.is_dir():
            raise MusicError("The music engine's input folder was not found.")
        name = f"sov_cover_{uuid.uuid4().hex[:10]}.mp3"
        staged["file"] = input_dir / name
        shutil.copyfile(audio_path(song_id), staged["file"])
        return build_cover_workflow(
            style=p["style"], lyrics=p["lyrics"], duration=p["duration"], seed=p["seed"], quality=p["quality"],
            audio_name=name, filename_prefix=f"audio/sov_{job_id}")

    def tag(song: dict[str, Any]) -> dict[str, Any]:
        song = {**song, "cover_of": song_id}
        music._meta_path(song["id"]).write_text(json.dumps(song, indent=2), encoding="utf-8")
        return song

    def cleanup() -> None:
        if "file" in staged:
            staged["file"].unlink(missing_ok=True)

    params.update(build_workflow=build, cleanup=cleanup, after_save=tag, auto_play=auto_play,
                  after_save_message="Saving the cover...")
    return music.create_job(params)
