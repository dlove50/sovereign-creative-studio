"""Music Lab playback on this computer, plus real waveform/spectrum data for the display.

Playback lives in the backend so Jarvis (voice) and the Music Lab screen share one
"now playing" state. Audio goes to the speakers through ffplay.
"""
from __future__ import annotations

import base64
import glob
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .. import config
from .music import MusicError, _check_id, _music_dir, audio_path, get_song

VIZ_FPS = 20
VIZ_BANDS = 24
VIZ_RATE = 22050

_IDLE: dict[str, Any] = {"proc": None, "song_id": None, "started_at": 0.0, "offset": 0.0, "duration": 0.0, "paused": False}
_playback: dict[str, Any] = dict(_IDLE)
_lock = threading.Lock()


def find_ffmpeg_tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    pattern = str(Path.home() / "AppData/Local/Microsoft/WinGet/Packages/BtbN.FFmpeg*/**/bin" / f"{name}.exe")
    hits = glob.glob(pattern, recursive=True)
    return hits[0] if hits else None


def audio_duration(path: Path) -> float | None:
    probe = find_ffmpeg_tool("ffprobe")
    if not probe:
        return None
    try:
        out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                             capture_output=True, text=True, timeout=20)
        return round(float(json.loads(out.stdout)["format"]["duration"]), 2)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return None


def _spawn_player(path: Path, start: float = 0.0) -> subprocess.Popen:
    ffplay = find_ffmpeg_tool("ffplay")
    if not ffplay:
        raise MusicError("No audio player (ffplay) was found on this computer.")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    seek = ["-ss", f"{start:.2f}"] if start > 0 else []
    return subprocess.Popen([ffplay, "-nodisp", "-autoexit", "-loglevel", "quiet", *seek,
                             "-volume", str(max(0, min(100, config.MUSIC_PLAYER_VOLUME))), str(path)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)


def _stop_locked() -> bool:
    proc = _playback["proc"]
    stopped = False
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        stopped = True
    _playback.update(_IDLE)
    return stopped


def play_song(song_id: str, start: float = 0.0) -> dict[str, Any]:
    """Start playing a library song through the speakers (replaces whatever is playing)."""
    song = get_song(song_id)
    if song is None:
        raise MusicError("Song not found.")
    with _lock:
        _stop_locked()
        duration = audio_duration(audio_path(song_id)) or float(song.get("duration_requested") or 0)
        start = max(0.0, min(float(start), max(duration - 0.5, 0.0))) if duration else 0.0
        proc = _spawn_player(audio_path(song_id), start) if start else _spawn_player(audio_path(song_id))
        _playback.update(proc=proc, song_id=song_id, started_at=time.time(), offset=start, duration=duration,
                         paused=False)
    return now_playing()


def _position_locked() -> float:
    if _playback["paused"]:
        return _playback["offset"]
    return min(_playback["offset"] + time.time() - _playback["started_at"], _playback["duration"] or 1e9)


def pause_playback() -> dict[str, Any]:
    """Pause the speakers; resume continues from the same spot."""
    with _lock:
        proc = _playback["proc"]
        if _playback["paused"] or proc is None or proc.poll() is not None:
            return now_playing_locked()
        position = _position_locked()
        song_id, duration = _playback["song_id"], _playback["duration"]
        _stop_locked()
        _playback.update(song_id=song_id, duration=duration, offset=position, paused=True)
    return now_playing()


def resume_playback() -> dict[str, Any]:
    with _lock:
        if not _playback["paused"]:
            return now_playing_locked()
        song_id, position, duration = _playback["song_id"], _playback["offset"], _playback["duration"]
        proc = _spawn_player(audio_path(song_id), position) if position else _spawn_player(audio_path(song_id))
        _playback.update(proc=proc, started_at=time.time(), offset=position, duration=duration, paused=False)
    return now_playing()


def seek_playback(seconds: float) -> dict[str, Any]:
    """Jump to a position, keeping the paused/playing state."""
    with _lock:
        song_id = _playback["song_id"]
        if song_id is None:
            raise MusicError("Nothing is playing.")
        duration = _playback["duration"]
        target = max(0.0, min(float(seconds), max(duration - 0.5, 0.0) if duration else float(seconds)))
        if _playback["paused"]:
            _playback["offset"] = target
            return now_playing_locked()
        _stop_locked()
        proc = _spawn_player(audio_path(song_id), target) if target else _spawn_player(audio_path(song_id))
        _playback.update(proc=proc, song_id=song_id, started_at=time.time(), offset=target, duration=duration,
                         paused=False)
    return now_playing()


def stop_playback() -> dict[str, Any]:
    with _lock:
        return {"stopped": _stop_locked()}


def now_playing_locked() -> dict[str, Any]:
    if _playback["paused"]:
        return {"playing": False, "paused": True, "song": get_song(_playback["song_id"]),
                "position": round(_playback["offset"], 2), "duration": _playback["duration"]}
    proc = _playback["proc"]
    if proc is None or proc.poll() is not None:
        if proc is not None:
            _playback.update(_IDLE)
        return {"playing": False, "paused": False, "song": None, "position": 0.0, "duration": 0.0}
    return {"playing": True, "paused": False, "song": get_song(_playback["song_id"]),
            "position": round(_position_locked(), 2), "duration": _playback["duration"]}


def now_playing() -> dict[str, Any]:
    with _lock:
        return now_playing_locked()


def _viz_path(song_id: str) -> Path:
    return _music_dir() / f"{song_id}.viz.json"


def visual_data(song_id: str) -> dict[str, Any]:
    """Band energies (uint8, base64, frames x bands) computed from the real audio at 20 fps."""
    _check_id(song_id)
    if get_song(song_id) is None:
        raise MusicError("Song not found.")
    cache = _viz_path(song_id)
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import numpy as np
    ffmpeg = find_ffmpeg_tool("ffmpeg")
    if not ffmpeg:
        raise MusicError("ffmpeg is needed to analyse the song.")
    raw = subprocess.run([ffmpeg, "-v", "error", "-i", str(audio_path(song_id)), "-f", "s16le", "-ac", "1",
                          "-ar", str(VIZ_RATE), "-"], capture_output=True, timeout=120).stdout
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size == 0:
        raise MusicError("The song contains no audio to analyse.")
    hop = VIZ_RATE // VIZ_FPS
    n_frames = max(1, len(samples) // hop)
    window = np.hanning(hop * 2)
    edges = np.unique(np.geomspace(2, hop, VIZ_BANDS + 1).astype(int))
    frames = np.zeros((n_frames, VIZ_BANDS), dtype=np.float32)
    for i in range(n_frames):
        chunk = samples[i * hop:i * hop + hop * 2]
        if len(chunk) < hop * 2:
            chunk = np.pad(chunk, (0, hop * 2 - len(chunk)))
        spectrum = np.abs(np.fft.rfft(chunk * window))
        for b in range(min(VIZ_BANDS, len(edges) - 1)):
            frames[i, b] = spectrum[edges[b]:max(edges[b] + 1, edges[b + 1])].mean()
    frames = np.log1p(frames * 40.0)
    peak = float(np.percentile(frames, 99.5)) or 1.0
    quantized = np.clip(frames / peak * 255.0, 0, 255).astype(np.uint8)
    data = {"fps": VIZ_FPS, "bands": VIZ_BANDS, "frames": n_frames, "duration": round(len(samples) / VIZ_RATE, 2),
            "data": base64.b64encode(quantized.tobytes()).decode("ascii")}
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data
