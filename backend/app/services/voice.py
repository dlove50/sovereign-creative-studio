"""Local-first text-to-speech (Phase 16B — real Piper backend).

`VOICE_BACKEND=piper` generates real `.wav` audio locally and offline via piper-tts;
`mock` (and any missing dependency/model) reports "setup required" and never fakes
audio. Cloud TTS is never the default. Readiness drives the UI.
"""
from __future__ import annotations

import difflib
import re
import time
import wave
from pathlib import Path

import httpx

from .. import config

VIBEVOICE_PREFIX = "vibevoice:"
_VIBEVOICE_POLL_SECONDS = 2.0
_VIBEVOICE_ATTEMPTS = 3
# Below this, the take has invented or dropped words (a clean take scores ~0.9-1.0).
_MIN_SCRIPT_MATCH = 0.75


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
    """Voices from the local VibeVoice Studio app (its presets and your clones); empty when it isn't running."""
    try:
        resp = httpx.get(f"{config.VIBEVOICE_BASE_URL}/api/voices", timeout=2.0)
        resp.raise_for_status()
        entries = [(v["name"], bool(v.get("preset"))) for v in resp.json().get("voices", [])]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        # The engine is asleep: read the recorded-voice folder so the voices still show up everywhere.
        from . import voice_studio

        entries = voice_studio.list_voice_names()
        if not entries:
            return []
    return [
        {
            "id": f"{VIBEVOICE_PREFIX}{name}",
            "label": f"{name} (VibeVoice {'preset' if preset else 'clone'})",
            "language": name.split("-")[0] if "-" in name else "en",
            "quality": "preset" if preset else "clone",
            "is_default": False,
            "ready": True,
        }
        for name, preset in entries
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
    Refuse while rendering; this check is not a distributed GPU reservation.
    ComfyUI being offline is fine, but an unknown queue must not be evicted.
    """
    base = config.COMFYUI_BASE_URL.rstrip("/")
    try:
        response = httpx.get(f"{base}/queue", timeout=5.0)
    except httpx.ConnectError:
        return  # No renderer to unload.
    except httpx.HTTPError as exc:
        raise RuntimeError("Cannot check the render queue. Retry the voice/AI request once ComfyUI is responsive.") from exc
    try:
        response.raise_for_status()
        queue = response.json()
        if not isinstance(queue, dict) or not all(isinstance(queue.get(k), list) for k in ("queue_running", "queue_pending")):
            raise ValueError("Unexpected queue response")
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Cannot verify that the render GPU is idle. No models were unloaded.") from exc
    if queue["queue_running"] or queue["queue_pending"]:
        raise RuntimeError("The render GPU is busy. Wait for current and queued renders to finish before starting this voice/AI request.")
    try:
        httpx.post(
            f"{base}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=10.0,
        )
    except httpx.HTTPError:
        pass


def _vibevoice_render(client: httpx.Client, script: str, voice_name: str) -> bytes:
    """One VibeVoice job: submit, wait, return the WAV bytes."""
    base = config.VIBEVOICE_BASE_URL
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
    return audio.content


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def script_match(expected: str, heard: str) -> float:
    """Word-level similarity (0-1) between the script and what Whisper heard."""
    return difflib.SequenceMatcher(None, _words(expected), _words(heard)).ratio()


def _heard(path: Path) -> str | None:
    """Local Whisper transcript of the clip, or None when no real transcriber is set up."""
    from .transcription import get_transcription_adapter

    if config.TRANSCRIPTION_BACKEND == "mock":
        return None
    try:
        result = get_transcription_adapter().transcribe(
            source_path=path, model_name=config.TRANSCRIPTION_MODEL_NAME
        )
    except RuntimeError:
        return None
    return result.transcript_text


def _vibevoice_speech(text: str, out_path: Path, voice_name: str) -> None:
    """Render `text` in a cloned voice via VibeVoice Studio, then unload its model
    so ComfyUI can use the GPU for the avatar video. Raises on any failure.

    VibeVoice occasionally invents speech before the script (seen: ~11 s of
    gibberish on a one-line script), so each take is checked with local Whisper
    and re-rendered with a fresh random seed if the words don't match.
    """
    base = config.VIBEVOICE_BASE_URL
    # VibeVoice scripts are "Speaker N:" lines; collapse the text onto one speaker line.
    script = "Speaker 1: " + " ".join(text.split())
    _free_comfyui_vram()
    from . import voice_studio  # starts the engine on demand (and swaps to a cloning model if needed)

    try:
        voice_studio.ensure_ready()
    except voice_studio.VoiceStudioError as exc:
        raise RuntimeError(str(exc)) from exc
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.Client(timeout=30.0) as client:
            try:
                for attempt in range(1, _VIBEVOICE_ATTEMPTS + 1):
                    out_path.write_bytes(_vibevoice_render(client, script, voice_name))
                    heard = _heard(out_path)
                    if heard is None or script_match(text, heard) >= _MIN_SCRIPT_MATCH:
                        break
                    if attempt == _VIBEVOICE_ATTEMPTS:
                        out_path.unlink(missing_ok=True)
                        raise RuntimeError(
                            f"VibeVoice did not read the script correctly after {attempt} tries "
                            f"(heard: {heard[:120]!r}). Try again or use a longer reference voice sample."
                        )
            finally:
                client.post(f"{base}/api/models/unload")
    except httpx.HTTPError as exc:
        raise RuntimeError(f"VibeVoice Studio is not reachable at {base}: {exc}") from exc
    if not out_path.is_file() or out_path.stat().st_size == 0:
        raise RuntimeError("VibeVoice produced no audio output.")
