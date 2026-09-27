"""Local-first text-to-speech (Phase 16B — real Piper backend).

`VOICE_BACKEND=piper` generates real `.wav` audio locally and offline via piper-tts;
`mock` (and any missing dependency/model) reports "setup required" and never fakes
audio. Cloud TTS is never the default. Readiness drives the UI.
"""
from __future__ import annotations

import time
import wave
from pathlib import Path

import httpx

from .. import config

VIBEVOICE_PREFIX = "vibevoice:"
_VIBEVOICE_POLL_SECONDS = 2.0


def _model_path() -> Path | None:
    """Resolve the default Piper .onnx voice model, or None if not found."""
    if config.VOICE_MODEL_PATH:
        path = Path(config.VOICE_MODEL_PATH)
        path = path if path.is_absolute() else config.BASE_DIR / path
        return path if path.is_file() else None
    model_dir = config.VOICE_MODEL_DIR
    if config.VOICE_MODEL_NAME:
        named = model_dir / f"{config.VOICE_MODEL_NAME}.onnx"
        if named.is_file():
            return named
    if model_dir.is_dir():
        found = sorted(model_dir.glob("*.onnx"))
        if found:
            return found[0]
    return None


def model_path_for_voice(voice_id: str | None) -> Path | None:
    """Resolve .onnx path for a specific voice_id, falling back to the default."""
    if voice_id:
        candidate = config.VOICE_MODEL_DIR / f"{voice_id}.onnx"
        if candidate.is_file():
            return candidate
    return _model_path()


def _piper_installed() -> bool:
    try:
        import piper  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def list_voices() -> list[dict]:
    """Return every valid (onnx + json config) Piper voice pair in VOICE_MODEL_DIR."""
    default_id = config.VOICE_MODEL_NAME or "en_US-lessac-low"
    voices: list[dict] = []
    model_dir = config.VOICE_MODEL_DIR
    if not model_dir.is_dir():
        return voices
    for onnx in sorted(model_dir.glob("*.onnx")):
        if not onnx.with_suffix(".onnx.json").is_file():
            continue
        voice_id = onnx.stem  # e.g. "en_US-lessac-low"
        # Parse language / quality from the stem convention: <lang>-<name>-<quality>
        parts = voice_id.split("-")
        language = parts[0] if parts else voice_id  # e.g. "en_US"
        quality = parts[-1] if len(parts) >= 3 else "standard"  # "low" / "medium" / "high"
        # Human-readable label: "en US lessac low"
        label = voice_id.replace("_", " ").replace("-", " ")
        voices.append({
            "id": voice_id,
            "label": label,
            "language": language,
            "quality": quality,
            "is_default": voice_id == default_id,
            "ready": True,
        })
    return voices + _vibevoice_voices()


def _vibevoice_voices() -> list[dict]:
    """Cloned voices from the local VibeVoice Studio app; empty when it isn't running."""
    try:
        resp = httpx.get(f"{config.VIBEVOICE_BASE_URL}/api/voices", timeout=2.0)
        resp.raise_for_status()
        names = [v["name"] for v in resp.json().get("voices", [])]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []
    return [
        {
            "id": f"{VIBEVOICE_PREFIX}{name}",
            "label": f"{name} (VibeVoice clone)",
            "language": name.split("-")[0] if "-" in name else "en",
            "quality": "clone",
            "is_default": False,
            "ready": True,
        }
        for name in names
    ]


def voice_readiness() -> dict:
    backend = config.VOICE_BACKEND
    if not config.VOICE_ENABLED:
        return {"backend": backend, "ready": False, "detail": "Voice features are turned off."}
    if backend == "piper":
        if not _piper_installed():
            return {
                "backend": "piper",
                "ready": False,
                "detail": "piper-tts is not installed. Run: pip install piper-tts",
            }
        model = _model_path()
        if model is None:
            return {
                "backend": "piper",
                "ready": False,
                "detail": "Local voice model not found. Download a Piper voice into the model dir or set VOICE_MODEL_PATH.",
            }
        return {"backend": "piper", "ready": True, "detail": f"Local Piper TTS ready ({model.name})."}
    return {
        "backend": "mock",
        "ready": False,
        "detail": "Local voice model setup required (Piper recommended).",
    }


def voice_ready() -> bool:
    return voice_readiness()["ready"]


def model_label() -> str:
    model = _model_path()
    return model.stem if model else (config.VOICE_MODEL_NAME or "none")


def generate_speech(text: str, out_path: Path, voice_id: str | None = None) -> None:
    """Synthesize `text` to a local WAV at `out_path` using Piper. Raises on failure;
    callers must only charge after this returns successfully (no faked output)."""
    if voice_id and voice_id.startswith(VIBEVOICE_PREFIX):
        _vibevoice_speech(text, out_path, voice_id[len(VIBEVOICE_PREFIX):])
        return
    from piper import PiperVoice

    model = model_path_for_voice(voice_id)
    if model is None:
        raise RuntimeError("Local Piper voice model not found.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    voice = PiperVoice.load(str(model))
    with wave.open(str(out_path), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RuntimeError("Piper produced no audio output.")


def _free_comfyui_vram() -> None:
    """Ask ComfyUI to drop its models so VibeVoice fits on the same 16 GB GPU.
    Best effort: ComfyUI may simply not be running."""
    try:
        httpx.post(
            f"{config.COMFYUI_BASE_URL}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=10.0,
        )
    except httpx.HTTPError:
        pass


def _vibevoice_speech(text: str, out_path: Path, voice_name: str) -> None:
    """Render `text` in a cloned voice via VibeVoice Studio, then unload its model
    so ComfyUI can use the GPU for the avatar video. Raises on any failure."""
    base = config.VIBEVOICE_BASE_URL
    # VibeVoice scripts are "Speaker N:" lines; collapse the text onto one speaker line.
    script = "Speaker 1: " + " ".join(text.split())
    _free_comfyui_vram()
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{base}/api/generate",
                json={"script": script, "voices": [voice_name], "cloneVoices": True},
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"VibeVoice rejected the request: {resp.text[:300]}")
            job_id = resp.json()["id"]

            deadline = time.monotonic() + config.VIBEVOICE_TIMEOUT_SECONDS
            while True:
                job = client.get(f"{base}/api/jobs/{job_id}").json()
                if job["status"] == "done":
                    break
                if job["status"] in ("failed", "cancelled"):
                    raise RuntimeError(f"VibeVoice {job['status']}: {job.get('error') or 'no detail'}")
                if time.monotonic() > deadline:
                    raise RuntimeError("VibeVoice timed out.")
                time.sleep(_VIBEVOICE_POLL_SECONDS)

            audio = client.get(f"{base}/api/jobs/{job_id}/audio")
            audio.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(audio.content)
            client.post(f"{base}/api/models/unload")
    except httpx.HTTPError as exc:
        raise RuntimeError(f"VibeVoice Studio is not reachable at {base}: {exc}") from exc
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RuntimeError("VibeVoice produced no audio output.")
