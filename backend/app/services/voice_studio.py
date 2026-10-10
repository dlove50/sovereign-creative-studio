"""Voice Studio: Sovereign's front door to VibeVoice.

The engine is F:\\AI\\VibeVoice\\sovereign_voice_service.py, a small service that reuses the VibeVoice demo's own engine
class, so every capability of the original app is kept (three models, 1 to 4 cloned speakers, voice upload, streaming,
stop, realtime preset voices, examples). This module starts and stops that service on demand, frees the graphics card
for it, forwards calls to it, and keeps finished clips in Sovereign's own library.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .. import config

VV_ROOT = Path(os.getenv("VIBEVOICE_ROOT", r"F:\AI\VibeVoice"))
VV_PYTHON = VV_ROOT / ".venv" / "Scripts" / "python.exe"
VV_SCRIPT = VV_ROOT / "sovereign_voice_service.py"
VV_PIDFILE = VV_ROOT / "vibevoice.pid"  # the Gradio demo's pid file (Start-VibeVoice-Studio.ps1)
VV_PORT = int(os.getenv("VOICE_STUDIO_PORT", "7861"))
VV_URL = f"http://127.0.0.1:{VV_PORT}"
BOOT_TIMEOUT = 300.0


class VoiceStudioError(Exception):
    pass


def _clips_dir() -> Path:
    path = Path(config.STORAGE_DIR) / "voice_studio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def installed() -> bool:
    return VV_PYTHON.is_file() and VV_SCRIPT.is_file()


# --- talking to the engine service ----------------------------------------------------------------

def call(method: str, path: str, body: dict | None = None, timeout: float = 30.0) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(VV_URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except ValueError:
            pass
        raise VoiceStudioError(str(detail)[:400]) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise VoiceStudioError("The voice engine is not running.") from exc


def fetch_bytes(path: str, timeout: float = 60.0) -> bytes:
    try:
        with urllib.request.urlopen(VV_URL + path, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as exc:
        raise VoiceStudioError("The voice engine is not running.") from exc


def upload_voice(filename: str, content: bytes) -> dict:
    boundary = "----sovereign" + uuid.uuid4().hex
    head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
    payload = head + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request(VV_URL + "/voices", data=payload, method="POST",
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except ValueError:
            pass
        raise VoiceStudioError(str(detail)[:400]) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise VoiceStudioError("The voice engine is not running.") from exc


def engine_status() -> dict[str, Any]:
    """{installed, online, ready, loading, model, kind, generating, voices}. Never raises."""
    base: dict[str, Any] = {"installed": installed(), "online": False, "ready": False, "loading": None, "model": None,
                            "kind": None, "generating": False, "voices": 0}
    if not base["installed"]:
        return base
    try:
        live = call("GET", "/status", timeout=2.0)
    except VoiceStudioError:
        return base
    return {**base, **live, "online": True}


# --- graphics memory: one heavy engine at a time on the 8 GB card -----------------------------------

def _free_comfy(base_url: str) -> None:
    """Ask an idle ComfyUI to unload its models. A busy one is left alone and the caller is told."""
    base = base_url.rstrip("/")
    try:
        with urllib.request.urlopen(base + "/queue", timeout=4.0) as response:
            queue = json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return  # not running: holds nothing
    if isinstance(queue, dict) and (queue.get("queue_running") or queue.get("queue_pending")):
        raise VoiceStudioError("The image, video or music engine is busy rendering. Wait for it to finish, then start the voice engine.")
    try:
        request = urllib.request.Request(base + "/free", data=json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        urllib.request.urlopen(request, timeout=10.0).close()
    except (urllib.error.URLError, OSError):
        pass


def stop_gradio_demo() -> bool:
    """Stop the original Gradio VibeVoice app if it is running (same as the Stop VibeVoice Studio icon)."""
    try:
        pid = int(VV_PIDFILE.read_text().strip())
    except (OSError, ValueError):
        return False
    result = subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, text=True)
    try:
        VV_PIDFILE.unlink()
    except OSError:
        pass
    return result.returncode == 0


def free_graphics_card() -> None:
    from .music import _release_main_engine  # lazy: music imports are heavy and optional here
    from . import music_compose

    _free_comfy(config.COMFYUI_BASE_URL)
    _free_comfy(config.MUSIC_COMFYUI_URL)
    music_compose.unload_models()
    _release_main_engine()


def start(model_label: str | None = None) -> dict[str, Any]:
    """Start the engine service if it is not running; returns immediately (the model loads in the background)."""
    if not installed():
        raise VoiceStudioError("VibeVoice is not installed where Sovereign expects it (F:\\AI\\VibeVoice).")
    current = engine_status()
    if current["online"]:
        return {"started": False, **current}
    stop_gradio_demo()
    free_graphics_card()
    env = {**os.environ, "HF_HOME": r"F:\AI\HuggingFaceCache", "HF_HUB_DISABLE_TELEMETRY": "1", "PYTHONUTF8": "1",
           "PYTHONIOENCODING": "utf-8"}
    ffmpeg_dir = VV_ROOT / "tools" / "ffmpeg" / "ffmpeg-8.1.1-essentials_build" / "bin"
    env["PATH"] = f"{ffmpeg_dir};{env.get('PATH', '')}"
    command = [str(VV_PYTHON), str(VV_SCRIPT), "--port", str(VV_PORT)]
    if model_label:
        command += ["--model", model_label]
    flags = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS
    log = open(VV_ROOT / "sovereign-voice-service.log", "ab")
    process = subprocess.Popen(command, cwd=str(VV_ROOT), env=env, stdout=log, stderr=log, creationflags=flags)
    from .process_power import disable_power_throttling_tree

    disable_power_throttling_tree(process.pid)  # Windows otherwise runs the hidden engine far slower
    return {"started": True, "pid": process.pid, **engine_status()}


def stop() -> bool:
    """Shut the engine down and give the card back."""
    try:
        call("POST", "/shutdown", {}, timeout=5.0)
        return True
    except VoiceStudioError:
        return False


def stop_if_running() -> None:
    """Called before songs and renders so they get the whole card."""
    if engine_status()["online"]:
        stop()
        deadline = time.time() + 15
        while time.time() < deadline and engine_status()["online"]:
            time.sleep(0.5)


# --- the clip library -----------------------------------------------------------------------------

_saved_jobs: dict[str, str] = {}  # engine job id -> clip id


def _meta_path(clip_id: str) -> Path:
    return _clips_dir() / f"{clip_id}.json"


def save_clip(job_id: str, job: dict[str, Any], script: str | None) -> dict[str, Any]:
    """Copy a finished engine job into Sovereign's library (once)."""
    if job_id in _saved_jobs:
        return get_clip(_saved_jobs[job_id])  # type: ignore[return-value]
    audio = fetch_bytes(f"/jobs/{job_id}/audio", timeout=120)
    clip_id = uuid.uuid4().hex[:12]
    (_clips_dir() / f"{clip_id}.wav").write_bytes(audio)
    seconds = max(0.0, (len(audio) - 44) / 2 / 24000)
    meta = {
        "id": clip_id, "kind": job.get("kind"), "script": (script or "")[:60000], "duration_seconds": round(seconds, 1),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "render_seconds": job.get("elapsed"), **(job.get("meta") or {}),
    }
    _meta_path(clip_id).write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _saved_jobs[job_id] = clip_id
    return meta


def get_clip(clip_id: str) -> dict[str, Any] | None:
    if not clip_id.isalnum() or not _meta_path(clip_id).exists() or not (_clips_dir() / f"{clip_id}.wav").exists():
        return None
    return json.loads(_meta_path(clip_id).read_text(encoding="utf-8"))


def list_clips() -> list[dict[str, Any]]:
    clips = []
    for meta in _clips_dir().glob("*.json"):
        clip = get_clip(meta.stem)
        if clip:
            clips.append(clip)
    clips.sort(key=lambda c: c.get("created_at", ""), reverse=True)
    return clips


def clip_audio_path(clip_id: str) -> Path | None:
    return _clips_dir() / f"{clip_id}.wav" if get_clip(clip_id) else None


def delete_clip(clip_id: str) -> bool:
    """Soft delete: moves the clip into storage/trash/voice_studio so it can be restored."""
    if not get_clip(clip_id):
        return False
    trash = Path(config.STORAGE_DIR) / "trash" / "voice_studio"
    trash.mkdir(parents=True, exist_ok=True)
    for suffix in (".wav", ".json"):
        source = _clips_dir() / f"{clip_id}{suffix}"
        if source.exists():
            source.replace(trash / source.name)
    return True


# --- the recorded-voice folder and on-demand start (used by avatars, movies, translate, slides, the Voices page) ---

_AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}


def voices_dir() -> Path:
    return VV_ROOT / "demo" / "voices"


def _is_builtin(name: str) -> bool:
    import re

    return bool(re.match(r"^(en|in|zh)-", name))


def list_voice_names() -> list[tuple[str, bool]]:
    """(name, is_builtin_preset) for every recorded voice, straight from the folder, so voices are listed even
    while the engine sleeps. Names match what the engine itself reports."""
    folder = voices_dir()
    if not installed() or not folder.is_dir():
        return []
    names = sorted(p.stem for p in folder.iterdir() if p.is_file() and p.suffix.lower() in _AUDIO_SUFFIXES)
    return [(n, _is_builtin(n)) for n in names]


def voice_file(name: str) -> Path | None:
    folder = voices_dir()
    if not installed() or not folder.is_dir():
        return None
    for path in folder.iterdir():
        if path.is_file() and path.stem == name and path.suffix.lower() in _AUDIO_SUFFIXES:
            return path
    return None


def add_voice_file(name: str, sample: Path) -> str:
    """Save a clean sample into the voice folder as <name>.wav (used while the engine sleeps)."""
    import re

    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")
    if not stem:
        raise VoiceStudioError("Give the voice a name.")
    if voice_file(stem) is not None:
        raise VoiceStudioError(f"A cloned voice named {stem} already exists. Pick a different name.")
    voices_dir().mkdir(parents=True, exist_ok=True)
    destination = voices_dir() / f"{stem}.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(sample), "-ac", "1", "-ar", "24000", str(destination)],
                   capture_output=True, check=False)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise VoiceStudioError("Could not read that recording.")
    return stem


def remove_voice_file(name: str) -> bool:
    """Move a cloned voice aside (never erased). Built-in voices cannot be removed."""
    path = voice_file(name)
    if path is None or _is_builtin(name):
        return False
    removed = voices_dir() / "_removed"
    removed.mkdir(parents=True, exist_ok=True)
    path.replace(removed / path.name)
    return True


def ensure_ready(timeout: float = BOOT_TIMEOUT) -> None:
    """Start the engine if needed and wait until a voice-cloning model is loaded."""
    if not engine_status()["online"]:
        start()
    deadline = time.time() + timeout
    state = engine_status()
    while not state["ready"]:
        if time.time() > deadline:
            raise VoiceStudioError("The voice engine did not finish loading in time.")
        time.sleep(2)
        state = engine_status()
    if state.get("kind") != "full":  # Realtime 0.5B cannot clone: swap to the best cloning model
        models = call("GET", "/models")["models"]
        full = next((m["label"] for m in models if m["kind"] == "full"), None)
        if full is None:
            raise VoiceStudioError("No voice-cloning model is installed.")
        call("POST", "/model", {"label": full}, timeout=600.0)
