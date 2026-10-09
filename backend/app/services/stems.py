"""Vocal / instrumental stems for Music Lab songs (Demucs, run in an isolated Python).

The split is cached next to the song as `<id>.stems/vocals.wav` and `instrumental.wav`
so a dub plate's version side and a sung special only pay for it once.
"""
from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
from pathlib import Path

from .. import config
from .music import MusicError, _check_id, _gpu_lock, _free_engine_memory, _music_dir, audio_path, get_song

STEM_NAMES = ("vocals", "instrumental")
SEPARATE_TIMEOUT = 900
_WORKER = Path(__file__).with_name("stems_worker.py")


def stems_dir(song_id: str) -> Path:
    return _music_dir() / f"{_check_id(song_id)}.stems"


def stem_path(song_id: str, name: str) -> Path:
    if name not in STEM_NAMES:
        raise MusicError("Unknown stem.")
    return stems_dir(song_id) / f"{name}.wav"


def has_stems(song_id: str) -> bool:
    return all(stem_path(song_id, n).is_file() and stem_path(song_id, n).stat().st_size > 0 for n in STEM_NAMES)


def stems_available() -> bool:
    return Path(config.MUSIC_STEMS_PYTHON).is_file() and _WORKER.is_file()


def ensure_stems(song_id: str, *, gpu_locked: bool = False) -> dict[str, Path]:
    """Return the vocal and instrumental files, splitting the song first if needed.

    Pass gpu_locked=True when the caller already holds the music GPU lock (the lock is not re-entrant).
    """
    if get_song(song_id) is None:
        raise MusicError("Song not found.")
    if has_stems(song_id):
        return {n: stem_path(song_id, n) for n in STEM_NAMES}
    if not stems_available():
        raise MusicError("The vocal splitter (Demucs) is not installed. See the Music Lab Engine tab.")
    out = stems_dir(song_id)
    partial = out.with_name(out.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    with contextlib.nullcontext() if gpu_locked else _gpu_lock:
        _free_engine_memory()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run([config.MUSIC_STEMS_PYTHON, str(_WORKER), str(audio_path(song_id)), str(partial)],
                                  capture_output=True, text=True, timeout=SEPARATE_TIMEOUT, creationflags=flags)
        except subprocess.TimeoutExpired as exc:
            shutil.rmtree(partial, ignore_errors=True)
            raise MusicError("Splitting the vocal took too long and was stopped.") from exc
    if proc.returncode != 0:
        shutil.rmtree(partial, ignore_errors=True)
        last = (proc.stderr.strip().splitlines() or ["unknown error"])[-1][:300]
        raise MusicError(f"Splitting the vocal failed: {last}")
    shutil.rmtree(out, ignore_errors=True)
    partial.rename(out)
    try:
        info = json.loads(proc.stdout.strip().splitlines()[-1])
        (out / "info.json").write_text(json.dumps(info), encoding="utf-8")
    except (ValueError, IndexError, OSError):
        pass
    return {n: stem_path(song_id, n) for n in STEM_NAMES}
