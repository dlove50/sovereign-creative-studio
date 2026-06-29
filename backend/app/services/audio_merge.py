"""Audio-onto-video merge using FFmpeg.

Accepts an existing local video (/storage/…) and either:
  * a pre-generated audio path (WAV/MP3), or
  * a Piper TTS text string (generates WAV first, then merges).

FFmpeg must be on PATH or FFMPEG_PATH must be set.  Piper TTS is optional;
its readiness is reported separately so the UI can show setup-required UI
instead of silently failing.

The merge is synchronous and typically takes under 1 second for 3-second
clips on local hardware.
"""
from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from .. import config
from .voice import generate_speech, list_voices, voice_readiness


def _ffmpeg() -> str | None:
    if config.FFMPEG_PATH:
        p = Path(config.FFMPEG_PATH)
        if p.is_file():
            return str(p)
        # WinGet path guard (see transcription.py)
        if p.name.lower() == "ffmpeg.exe":
            return str(p)
    return shutil.which("ffmpeg")


def audio_merge_readiness() -> dict:
    ffmpeg_bin = _ffmpeg()
    piper = voice_readiness()
    voices = list_voices() if piper["ready"] else []
    default_id = config.VOICE_MODEL_NAME or (voices[0]["id"] if voices else None)
    return {
        "ffmpeg": ffmpeg_bin is not None,
        "ffmpeg_path": ffmpeg_bin,
        "piper": piper["ready"],
        "piper_detail": piper["detail"],
        "ready": ffmpeg_bin is not None,
        "detail": (
            "FFmpeg available; audio merge is ready."
            if ffmpeg_bin
            else "FFmpeg not found on PATH. Install FFmpeg to enable audio merge."
        ),
        "default_voice": default_id,
        "voices": voices,
    }


def merge_audio_onto_video(
    source_video: Path,
    audio: Path,
    out_path: Path,
) -> None:
    """Merge *audio* onto *source_video*, writing result to *out_path*.

    Video stream is copied (no re-encode). Audio is encoded as AAC.
    Duration is clamped to the shorter of video or audio (-shortest).
    Raises RuntimeError on FFmpeg failure.
    """
    ffmpeg_bin = _ffmpeg()
    if ffmpeg_bin is None:
        raise RuntimeError(
            "FFmpeg not found. Install FFmpeg and add it to PATH "
            "(or set FFMPEG_PATH) to enable audio merge."
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y",                        # overwrite output
        "-i", str(source_video),     # video input
        "-i", str(audio),            # audio input
        "-map", "0:v:0",             # take video stream from input 0
        "-map", "1:a:0",             # take audio stream from input 1
        "-c:v", "copy",              # copy video without re-encoding
        "-c:a", "aac",               # encode audio as AAC
        "-b:a", "128k",
        "-shortest",                 # end at the shorter stream
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg audio merge failed (exit {result.returncode}): {result.stderr[-400:]}"
        )
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg produced no output file.")


_PREVIEW_TTL_SECONDS = 3600  # delete previews older than 1 hour


def _cleanup_old_previews(voices_dir: Path) -> None:
    """Delete preview_*.wav files older than _PREVIEW_TTL_SECONDS. Best-effort."""
    import time
    now = time.time()
    for f in voices_dir.glob("preview_*.wav"):
        try:
            if now - f.stat().st_mtime > _PREVIEW_TTL_SECONDS:
                f.unlink(missing_ok=True)
        except OSError:
            pass


def generate_voice_preview(tts_text: str, voice_id: str | None = None) -> Path:
    """Generate a Piper TTS WAV preview and return its path under STORAGE_DIR/voices/."""
    piper_state = voice_readiness()
    if not piper_state["ready"]:
        raise RuntimeError(f"Piper TTS is not ready: {piper_state['detail']}")
    voices_dir = config.STORAGE_DIR / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_old_previews(voices_dir)
    preview_id = uuid.uuid4().hex
    wav_path = voices_dir / f"preview_{preview_id}.wav"
    generate_speech(tts_text, wav_path, voice_id=voice_id)
    return wav_path


def merge_tts_onto_video(
    source_video_url: str,
    tts_text: str,
    voice_id: str | None = None,
) -> Path:
    """Generate TTS from *tts_text* (Piper) and merge onto *source_video_url*.

    Returns the local Path of the merged output file under STORAGE_DIR/videos/.
    Raises RuntimeError if Piper is not ready or FFmpeg is missing.
    """
    readiness = audio_merge_readiness()
    if not readiness["ffmpeg"]:
        raise RuntimeError(readiness["detail"])
    piper_state = voice_readiness()
    if not piper_state["ready"]:
        raise RuntimeError(f"Piper TTS is not ready: {piper_state['detail']}")

    rel = source_video_url.lstrip("/").removeprefix("storage/")
    source_video = config.STORAGE_DIR / rel
    if not source_video.is_file():
        raise RuntimeError(f"Source video not found: {source_video_url}")

    job_id = uuid.uuid4().hex
    voices_dir = config.STORAGE_DIR / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    wav_path = voices_dir / f"{job_id}.wav"
    generate_speech(tts_text, wav_path, voice_id=voice_id)

    out_dir = config.STORAGE_DIR / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{job_id}_audio.mp4"
    merge_audio_onto_video(source_video, wav_path, out_path)

    try:
        wav_path.unlink()
    except OSError:
        pass

    return out_path
