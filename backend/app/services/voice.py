"""Local-first text-to-speech (Phase 16B — real Piper backend).

`VOICE_BACKEND=piper` generates real `.wav` audio locally and offline via piper-tts;
`mock` (and any missing dependency/model) reports "setup required" and never fakes
audio. Cloud TTS is never the default. Readiness drives the UI.
"""
from __future__ import annotations

import wave
from pathlib import Path

from .. import config


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
    return voices


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
