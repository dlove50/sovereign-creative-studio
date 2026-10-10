"""Music Lab import: your own songs in the library, with the vocal split out and the lyrics written down.

An imported file becomes an ordinary library song (``<id>.mp3`` + ``<id>.json``) marked ``provider: imported``,
so it plays, visualises and dubs like any made song. Lyrics are transcribed by local Whisper from the isolated
vocal (Demucs), as timed lines that the Stage highlights while the song plays.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .. import config
from . import stems
from .dubplate import _peaks
from .music import MusicError, _meta_path, _music_dir, audio_path, get_song
from .music_playback import audio_duration, find_ffmpeg_tool

IMPORT_SUFFIXES = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".opus", ".wma")
MAX_IMPORT_BYTES = 200 * 1024 * 1024
MAX_LINES = 400
MAX_LINE_CHARS = 300
PEAK_RATE = 11025
CONVERT_TIMEOUT = 300

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _ffmpeg() -> str:
    ffmpeg = find_ffmpeg_tool("ffmpeg")
    if not ffmpeg:
        raise MusicError("ffmpeg is needed to import songs.")
    return ffmpeg


def _title_from(filename: str) -> str:
    stem = re.sub(r"[_]+", " ", Path(filename or "").stem).strip()
    return re.sub(r"\s+", " ", stem)[:80] or "Imported song"


# --- import -----------------------------------------------------------------------------------

def import_song(filename: str, data: bytes) -> dict[str, Any]:
    """Add one audio file to the library and return its song record."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in IMPORT_SUFFIXES:
        raise MusicError("Choose an audio file: MP3, WAV, M4A, FLAC, OGG, AAC, OPUS or WMA.")
    if not data:
        raise MusicError("That file is empty.")
    if len(data) > MAX_IMPORT_BYTES:
        raise MusicError("That file is larger than 200 MB.")
    song_id = uuid.uuid4().hex[:12]
    target = audio_path(song_id)
    source = _music_dir() / f".import-{song_id}{suffix}"
    source.write_bytes(data)
    try:
        if suffix == ".mp3":
            shutil.copyfile(source, target)  # keep the original quality; the check below proves it decodes
        else:
            subprocess.run([_ffmpeg(), "-v", "error", "-y", "-i", str(source), "-vn", "-c:a", "libmp3lame", "-b:a", "320k",
                            str(target)], capture_output=True, timeout=CONVERT_TIMEOUT, check=False)
        seconds = audio_duration(target) if target.is_file() and target.stat().st_size else None
        if not seconds:
            target.unlink(missing_ok=True)
            raise MusicError("Could not read that file as audio.")
    finally:
        source.unlink(missing_ok=True)
    song = {
        "id": song_id,
        "title": _title_from(filename),
        "style": "",
        "lyrics": "",
        "instrumental": False,
        "duration_requested": round(seconds),
        "seed": 0,
        "quality": "",
        "provider": "imported",
        "favorite": False,
        "size_bytes": target.stat().st_size,
        "generation_seconds": 0,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_filename": Path(filename).name[:200],
    }
    _meta_path(song_id).write_text(json.dumps(song, indent=2), encoding="utf-8")
    return song


# --- lyrics -----------------------------------------------------------------------------------

def transcribe_lines(vocals: Path) -> list[dict[str, Any]]:
    """Timed lines [{start, end, text}] heard in an isolated vocal, by local Whisper on the CPU."""
    from faster_whisper import WhisperModel  # type: ignore

    options = {"device": config.TRANSCRIPTION_DEVICE, "compute_type": config.TRANSCRIPTION_COMPUTE_TYPE}
    try:  # use the copy already on this computer without asking the model hub online
        model = WhisperModel(config.MUSIC_LYRICS_WHISPER_MODEL, local_files_only=True, **options)
    except Exception:  # noqa: BLE001 - not downloaded yet: fetch the model once
        model = WhisperModel(config.MUSIC_LYRICS_WHISPER_MODEL, **options)
    segments, _ = model.transcribe(str(vocals), beam_size=5, vad_filter=True)
    return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
            for s in segments if s.text.strip()]


def _save_lines(song_id: str, lines: list[dict[str, Any]], source: str) -> dict[str, Any]:
    song = get_song(song_id)
    if song is None:
        raise MusicError("Song not found.")
    song["lyric_lines"] = lines
    song["lyrics_source"] = source
    # Lyrics written for a made song stay; an imported song's lyrics are what was heard.
    if song.get("provider") == "imported" or not song.get("lyrics", "").strip():
        song["lyrics"] = "\n".join(line["text"] for line in lines)
    _meta_path(song_id).write_text(json.dumps(song, indent=2), encoding="utf-8")
    return song


def _update(job_id: str, **fields: Any) -> None:
    with _jobs_lock:
        _jobs[job_id].update(fields)


def _run(job_id: str, song_id: str) -> None:
    try:
        _update(job_id, status="running", stage="splitting", message="Separating the vocal from the music...")
        vocals = stems.ensure_stems(song_id)["vocals"]
        _update(job_id, stage="transcribing", message="Listening to the vocal and writing the lyrics down...")
        lines = transcribe_lines(vocals)
        if not lines:
            raise MusicError("No singing was heard in this song.")
        song = _save_lines(song_id, lines, "whisper")
        _update(job_id, status="done", stage="done", message=f"{len(lines)} lines written down.", song=song)
    except MusicError as exc:
        _update(job_id, status="error", stage="error", message=str(exc), error=str(exc))
    except Exception as exc:  # noqa: BLE001 - Whisper/ffmpeg failures must end the job with a readable reason
        reason = f"Transcribing the lyrics failed: {exc}"[:300]
        _update(job_id, status="error", stage="error", message=reason, error=reason)


def _spawn(fn: Callable[..., None], *args: Any) -> None:
    threading.Thread(target=fn, args=args, daemon=True, name="music-lyrics").start()


def start_transcription(song_id: str, *, run_in_background: bool = True) -> dict[str, Any]:
    if get_song(song_id) is None:
        raise MusicError("Song not found.")
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"id": job_id, "song_id": song_id, "status": "queued", "stage": "queued",
                         "message": "Waiting to start...", "error": None, "song": None}
    if run_in_background:
        _spawn(_run, job_id, song_id)
    else:
        _run(job_id, song_id)
    return get_job(job_id)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def save_lyric_lines(song_id: str, lines: list[dict[str, Any]]) -> dict[str, Any]:
    """Store corrected lines. Each keeps its timing; times must run forward."""
    if len(lines) > MAX_LINES:
        raise MusicError(f"At most {MAX_LINES} lines.")
    clean: list[dict[str, Any]] = []
    for line in lines:
        start, end = float(line["start"]), float(line["end"])
        text = re.sub(r"\s+", " ", str(line.get("text", ""))).strip()[:MAX_LINE_CHARS]
        if start < 0 or end < start:
            raise MusicError("Each line must end after it starts.")
        if text:
            clean.append({"start": round(start, 2), "end": round(end, 2), "text": text})
    return _save_lines(song_id, clean, "edited")


# --- vocal waveform ---------------------------------------------------------------------------

def vocal_waveform(song_id: str) -> dict[str, Any]:
    """{has_stems, duration, peaks (base64 uint8)} for the isolated vocal, or has_stems False before a split."""
    if get_song(song_id) is None:
        raise MusicError("Song not found.")
    if not stems.has_stems(song_id):
        return {"has_stems": False, "duration": 0, "peaks": None}
    import numpy as np

    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(stems.stem_path(song_id, "vocals")), "-f", "s16le",
                          "-ac", "1", "-ar", str(PEAK_RATE), "-"], capture_output=True, timeout=120).stdout
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size == 0:
        raise MusicError("The vocal track contains no audio.")
    return {"has_stems": True, "duration": round(samples.size / PEAK_RATE, 2),
            "peaks": base64.b64encode(_peaks(samples)).decode("ascii")}
