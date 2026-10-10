"""Voice Studio: VibeVoice text-to-speech and voice cloning, driven from inside Sovereign.

VibeVoice runs as its own small local service (the "VibeVoice Studio" app, port 8010). This module starts and
stops that service, forwards requests to it, and keeps the finished clips in Sovereign's own storage so the
history survives restarts of either program. Nothing leaves this machine.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .. import config

CLIP_ID_RE = re.compile(r"^[a-f0-9]{12}$")
VOICE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SAMPLE_RATE = 24000
REQUEST_TIMEOUT = 15.0
MAX_UPLOAD_BYTES = 60 * 1024 * 1024
JOB_STATUS = {"queued": "running", "running": "running", "done": "done", "failed": "error", "cancelled": "stopped"}

_start_lock = threading.Lock()
_started_process: subprocess.Popen | None = None


class VoiceStudioError(RuntimeError):
    """A reason the voice studio cannot do what was asked, in words fit to show."""

    def __init__(self, message: str, status: int = 503) -> None:
        super().__init__(message)
        self.status = status


def _app_dir() -> Path:
    return Path(config.VIBEVOICE_APP_DIR)


def _python() -> Path:
    return _app_dir() / ".venv" / "Scripts" / "python.exe"


LEGACY_PORT = 8010  # where the standalone VibeVoice Studio shortcut puts it (port 8010 is also the OCR service's)


def _looks_like_vibevoice(port: int) -> bool:
    try:
        response = httpx.get(f"http://127.0.0.1:{port}/api/status", timeout=1.2)
        return response.status_code == 200 and "modelState" in response.json()
    except (httpx.HTTPError, ValueError):
        return False


def _port() -> int:
    """Use a VibeVoice Studio that is already running (for example started from its desktop shortcut); otherwise ours."""
    if config.VIBEVOICE_PORT != LEGACY_PORT and _looks_like_vibevoice(LEGACY_PORT):
        return LEGACY_PORT
    return config.VIBEVOICE_PORT


def _base() -> str:
    return f"http://127.0.0.1:{_port()}"


def _outputs_dir() -> Path:
    return _app_dir() / "outputs"


def _clips_dir() -> Path:
    path = config.STORAGE_DIR / "voice-studio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def installed() -> bool:
    return _python().is_file() and (_app_dir() / "backend" / "app.py").is_file()


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    try:
        response = httpx.request(method, _base() + path, timeout=kwargs.pop("timeout", REQUEST_TIMEOUT), **kwargs)
    except httpx.HTTPError as exc:
        raise VoiceStudioError("The voice engine is not running. Start it from Voice Studio.") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise VoiceStudioError(str(detail)[:400], status=response.status_code if response.status_code < 500 else 502)
    return response


def _json(method: str, path: str, **kwargs: Any) -> Any:
    return _request(method, path, **kwargs).json()


def is_online() -> bool:
    try:
        return httpx.get(_base() + "/api/status", timeout=1.5).status_code == 200
    except httpx.HTTPError:
        return False


def _model_kind(_name: str | None) -> str | None:
    # The installed checkpoints (7B and 1.5B) are the full multi-speaker models. A streaming "realtime"
    # model would be reported here as "realtime" if one were installed.
    return "full" if _name else None


# ---- Engine process -------------------------------------------------------------------------------------------

def status() -> dict[str, Any]:
    out: dict[str, Any] = {"installed": installed(), "online": False, "ready": False, "loading": None, "model": None,
                           "kind": None, "generating": False, "voices": 0}
    if not out["installed"] or not is_online():
        return out
    out["online"] = True
    try:
        data = _json("GET", "/api/status")
        out["ready"] = data.get("modelState") == "ready"
        loaded = data.get("loadedModel")
        out["model"] = loaded
        out["kind"] = _model_kind(loaded)
        if data.get("modelState") == "loading":
            out["loading"] = loaded or "model"
        out["generating"] = bool(data.get("queueDepth")) or any(
            j.get("status") == "running" for j in _json("GET", "/api/jobs").get("jobs", []))
        out["voices"] = len(_json("GET", "/api/voices").get("voices", []))
    except VoiceStudioError:
        pass
    return out


def start(model: str | None = None) -> dict[str, Any]:
    global _started_process
    if not installed():
        raise VoiceStudioError(f"VibeVoice Studio was not found at {_app_dir()}. Set VIBEVOICE_APP_DIR.", 404)
    with _start_lock:
        started = False
        if not is_online():
            env = None
            if model:
                import os
                env = {**os.environ, "VIBEVOICE_MODEL": _safe_model(model)}
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            _started_process = subprocess.Popen(
                [str(_python()), "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(config.VIBEVOICE_PORT)],
                cwd=str(_app_dir()), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            started = True
            for _ in range(60):
                if is_online():
                    break
                time.sleep(0.5)
        elif model:
            switch_model(model)
    return {**status(), "started": started}


def stop() -> dict[str, bool]:
    global _started_process
    stopped = False
    if _started_process is not None and _started_process.poll() is None:
        _started_process.terminate()
        stopped = True
    _started_process = None
    # Also stop an instance that was started by hand on the same port (this user's own local service).
    script = (f"Get-NetTCPConnection -LocalPort {int(_port())} -State Listen -ErrorAction SilentlyContinue | "
              "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=30,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    time.sleep(0.5)
    return {"stopped": stopped or not is_online()}


# ---- Models, voices, examples -----------------------------------------------------------------------------------

def _present_models() -> list[dict[str, Any]]:
    data = _json("GET", "/api/models")
    return [m for m in data.get("models", []) if m.get("present")]


def _safe_model(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", name or ""):
        raise VoiceStudioError("That is not a model name.", 400)
    return name


def models() -> dict[str, Any]:
    present = _present_models()
    st = _json("GET", "/api/status")
    return {"current": st.get("loadedModel"),
            "models": [{"label": m["name"], "kind": "full", "title": m.get("label"), "note": m.get("note")} for m in present]}


def switch_model(name: str) -> dict[str, Any]:
    _json("POST", f"/api/models/{_safe_model(name)}/select")
    return {"message": f"Switching to {name}. Large models take a minute to load.", "current": name, "kind": "full"}


def voices() -> dict[str, Any]:
    items = _json("GET", "/api/voices").get("voices", [])
    return {"voices": [{"name": v["name"], "file": v["name"] + ".wav", "preset": bool(v.get("preset"))} for v in items],
            "realtime": []}


def voice_audio(name: str) -> bytes:
    if not VOICE_NAME_RE.match(name):
        raise VoiceStudioError("Unknown voice.", 404)
    return _request("GET", f"/api/voices/{name}/preview").content


def add_voice(filename: str, data: bytes) -> dict[str, Any]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise VoiceStudioError("That file is too large (60 MB limit). A 30 second clean sample is enough.", 413)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(filename or "voice").stem).strip("-")[:64]
    if not stem:
        raise VoiceStudioError("Give the file a name with letters or numbers.", 400)
    response = _request("POST", "/api/voices", params={"name": stem}, files={"file": (filename or "voice.wav", data)}, timeout=120)
    added = response.json().get("name", stem)
    return {"added": added, "voices": [v["name"] for v in voices()["voices"]]}


def delete_voice(name: str) -> dict[str, Any]:
    if not VOICE_NAME_RE.match(name):
        raise VoiceStudioError("Unknown voice.", 404)
    return _json("DELETE", f"/api/voices/{name}")


def examples() -> dict[str, Any]:
    out = []
    for item in _json("GET", "/api/examples").get("examples", []):
        try:
            script = _json("GET", f"/api/examples/{item['id']}").get("script", "")
        except VoiceStudioError:
            continue
        out.append({"name": item.get("title") or item["id"], "num_speakers": item.get("speakers", 2), "script": script,
                    "minutes": item.get("minutes")})
    return {"examples": out}


# ---- Generating ----------------------------------------------------------------------------------------------------

_pending: dict[str, dict[str, Any]] = {}
_pending_lock = threading.Lock()


def generate(script: str, num_speakers: int, speakers: list[str], cfg_scale: float, inference_steps: int, seed: int,
             disable_voice_cloning: bool) -> dict[str, str]:
    if not script.strip():
        raise VoiceStudioError("Write a script first.", 400)
    names = [s for s in speakers[:max(1, num_speakers)] if VOICE_NAME_RE.match(s)]
    if not names:
        raise VoiceStudioError("Choose a voice for each speaker.", 400)
    body = {"script": script, "voices": names, "cfgScale": cfg_scale, "inferenceSteps": inference_steps,
            "seed": seed, "cloneVoices": not disable_voice_cloning}
    job = _json("POST", "/api/generate", json=body)
    with _pending_lock:
        _pending[job["id"]] = {"script": script, "speakers": names, "cfg_scale": cfg_scale,
                               "inference_steps": inference_steps, "seed": seed}
    return {"id": job["id"]}


def _wav_seconds(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return round(w.getnframes() / float(w.getframerate()), 1)
    except (wave.Error, OSError):
        return 0.0


def _clip_meta(clip_id: str) -> dict[str, Any] | None:
    meta = _clips_dir() / f"{clip_id}.json"
    return json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else None


def _save_clip(job: dict[str, Any]) -> dict[str, Any] | None:
    """Copy a finished render into Sovereign's storage with its settings, once."""
    clip_id = job["id"]
    existing = _clip_meta(clip_id)
    if existing:
        return existing
    source = _outputs_dir() / f"{clip_id}.wav"
    if not source.is_file():
        return None
    with _pending_lock:
        request = _pending.pop(clip_id, {})
    target = _clips_dir() / f"{clip_id}.wav"
    shutil.copyfile(source, target)
    clip = {
        "id": clip_id, "kind": "podcast", "script": request.get("script", ""),
        "duration_seconds": job.get("audioSeconds") or _wav_seconds(target),
        "created_at": datetime.fromtimestamp(job.get("createdAt") or time.time(), timezone.utc).isoformat(timespec="seconds"),
        "render_seconds": job.get("elapsedSeconds"), "model": job.get("model"),
        "speakers": request.get("speakers") or job.get("voices") or [], "cfg_scale": request.get("cfg_scale"),
        "inference_steps": request.get("inference_steps"), "seed": request.get("seed"),
    }
    (_clips_dir() / f"{clip_id}.json").write_text(json.dumps(clip, indent=2), encoding="utf-8")
    return clip


def job(job_id: str) -> dict[str, Any]:
    if not CLIP_ID_RE.match(job_id):
        raise VoiceStudioError("Unknown job.", 404)
    data = _json("GET", f"/api/jobs/{job_id}")
    status_text = JOB_STATUS.get(data.get("status"), "running")
    out: dict[str, Any] = {
        "id": job_id, "kind": "podcast", "status": status_text, "log": "\n".join(data.get("log") or []),
        "error": data.get("error"), "chunk_count": 0, "streamed_seconds": 0.0,
        "elapsed": data.get("elapsedSeconds") or 0.0, "has_audio": status_text == "done",
    }
    if status_text == "done":
        clip = _save_clip(data)
        if clip:
            out["clip"] = clip
    return out


def chunks(job_id: str, after: int) -> dict[str, Any]:
    """Full-quality models render a whole clip at once, so there are no live chunks to stream."""
    current = job(job_id)
    return {"sample_rate": SAMPLE_RATE, "next": after, "chunks": [], "status": current["status"]}


def stop_job(job_id: str) -> dict[str, bool]:
    if not CLIP_ID_RE.match(job_id):
        raise VoiceStudioError("Unknown job.", 404)
    try:
        _json("POST", f"/api/jobs/{job_id}/cancel")
    except VoiceStudioError as exc:
        raise VoiceStudioError(
            "This render has already started and runs as one piece, so it cannot be interrupted. "
            "It will finish in a moment; queued renders can be cancelled.", 409) from exc
    return {"stopping": True}


def realtime(*_args: Any, **_kwargs: Any) -> dict[str, str]:
    raise VoiceStudioError(
        "Real-time speech needs the VibeVoice Realtime model, which is not installed on this PC yet. "
        "Conversation and podcast voices work with the 7B and 1.5B models.", 409)


# ---- Saved clips -----------------------------------------------------------------------------------------------------

def clips() -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for meta in _clips_dir().glob("*.json"):
        if CLIP_ID_RE.match(meta.stem) and (_clips_dir() / f"{meta.stem}.wav").exists():
            try:
                items[meta.stem] = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
    # Renders made earlier in the standalone VibeVoice Studio show up too, once, with what is known about them.
    outputs = _outputs_dir()
    if outputs.is_dir():
        for wav in outputs.glob("*.wav"):
            if CLIP_ID_RE.match(wav.stem) and wav.stem not in items and not (_clips_dir() / f"{wav.stem}.deleted").exists():
                target = _clips_dir() / f"{wav.stem}.wav"
                if not target.exists():
                    shutil.copyfile(wav, target)
                clip = {"id": wav.stem, "kind": "podcast", "script": "(rendered earlier in VibeVoice Studio)",
                        "duration_seconds": _wav_seconds(target),
                        "created_at": datetime.fromtimestamp(wav.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
                        "speakers": []}
                (_clips_dir() / f"{wav.stem}.json").write_text(json.dumps(clip, indent=2), encoding="utf-8")
                items[wav.stem] = clip
    ordered = sorted(items.values(), key=lambda c: c.get("created_at", ""), reverse=True)
    return [{**c, "audio_url": f"/api/voice-studio/clips/{c['id']}/audio"} for c in ordered]


def clip_audio_path(clip_id: str) -> Path:
    if not CLIP_ID_RE.match(clip_id):
        raise VoiceStudioError("Unknown clip.", 404)
    path = _clips_dir() / f"{clip_id}.wav"
    if not path.is_file():
        raise VoiceStudioError("Clip not found.", 404)
    return path


def delete_clip(clip_id: str) -> bool:
    if not CLIP_ID_RE.match(clip_id):
        raise VoiceStudioError("Unknown clip.", 404)
    found = False
    for path in (_clips_dir() / f"{clip_id}.wav", _clips_dir() / f"{clip_id}.json"):
        if path.exists():
            path.unlink()
            found = True
    # Remember the deletion so an earlier render from the standalone app (which is left untouched) is not re-imported.
    (_clips_dir() / f"{clip_id}.deleted").write_text("", encoding="utf-8")
    return found


# --- helpers the rest of Sovereign uses (voice list, voice cloning, songs freeing the card) ---------
# vibevoice-app keeps its built-in voices in voices/*.wav and cloned ones in voices/custom/*.wav, so these work
# straight from the folders even while the engine sleeps.
BOOT_TIMEOUT = 300.0


def voices_dir() -> Path:
    return _app_dir() / "voices"


def list_voice_names() -> list[tuple[str, bool]]:
    """(name, is_builtin_preset) for every recorded voice, presets first, as the engine lists them."""
    if not installed():
        return []
    presets = [(p.stem, True) for p in sorted(voices_dir().glob("*.wav"))]
    custom = [(p.stem, False) for p in sorted((voices_dir() / "custom").glob("*.wav"))]
    return presets + custom


def voice_file(name: str) -> Path | None:
    if not installed() or not VOICE_NAME_RE.match(name):
        return None
    for path in (voices_dir() / "custom" / f"{name}.wav", voices_dir() / f"{name}.wav"):
        if path.is_file():
            return path
    return None


def add_voice_file(name: str, sample: Path) -> str:
    """Save a recording as a cloned voice (24 kHz mono WAV in voices/custom). Returns the voice name."""
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", name).strip("-")[:64]
    if not stem:
        raise VoiceStudioError("Give the voice a name.", 400)
    if voice_file(stem) is not None:
        raise VoiceStudioError(f"A voice named {stem} already exists. Pick a different name.", 409)
    destination = voices_dir() / "custom" / f"{stem}.wav"
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(sample), "-ac", "1", "-ar", str(SAMPLE_RATE), str(destination)],
                   capture_output=True, check=False)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise VoiceStudioError("Could not read that recording.", 400)
    return stem


def remove_voice_file(name: str) -> bool:
    """Move a cloned voice aside into voices/custom/_removed (never erased). Built-in voices are not removed."""
    path = voice_file(name)
    if path is None or path.parent != voices_dir() / "custom":
        return False
    removed = path.parent / "_removed"
    removed.mkdir(exist_ok=True)
    path.replace(removed / path.name)
    return True


def ensure_ready(timeout: float = BOOT_TIMEOUT) -> None:
    """Start the engine if needed and wait until its model has loaded (it loads one on start)."""
    if not status()["online"]:
        start()
    deadline = time.time() + timeout
    while not status()["ready"]:
        if time.time() >= deadline:
            raise VoiceStudioError("The voice engine did not finish loading in time.")
        time.sleep(2)


def stop_if_running() -> None:
    """Called before songs and renders so they get the whole graphics card."""
    if is_online():
        stop()
