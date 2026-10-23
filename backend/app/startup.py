"""Startup configuration checks.

Emits clear, non-fatal warnings for common misconfigurations (missing API key,
unknown backend, unwritable storage) so problems are obvious in the logs instead
of surfacing later as cryptic job failures. Returns the warnings so they can be
asserted in tests."""
import logging
import os

from .config import (
    COPY_BACKEND,
    GENERATOR_BACKEND,
    OPENAI_API_KEY,
    PRODUCT_SCENE_BACKEND,
    STORAGE_DIR,
    TRANSCRIPTION_BACKEND,
    VIDEO_BACKEND,
)
from .services.transcription import transcription_readiness

logger = logging.getLogger("sovereign.startup")

_VALID_IMAGE_BACKENDS = {"mock", "comfyui"}
_VALID_COPY_BACKENDS = {
    "mock",
    "openai",
    "ollama",
    "claude",
    "gemini",
    "local-qwen",
    "local-deepseek",
}


def run_startup_checks() -> list[str]:
    warnings: list[str] = []

    # Repair loose permissions on the secrets folder before anything reads it.
    # It holds the session signing key and every cloud provider API key, and
    # under the default umask it is created world-readable. Done here as well
    # as at the writers, because a key written by an earlier version stays
    # loose until something fixes it in place.
    try:
        from .auth import harden_secrets_dir

        tightened = harden_secrets_dir()
    except Exception:  # noqa: BLE001 - never let this stop the app booting
        logger.exception("[startup] Could not check secrets folder permissions")
    else:
        if tightened:
            logger.warning(
                "[startup] Tightened permissions on %d secrets path(s): %s",
                len(tightened), ", ".join(tightened),
            )

    # Anonymous owner-admin access is fine on a machine that only listens to
    # itself and catastrophic the moment it does not. Nothing noticed that
    # combination before this.
    try:
        from . import config as _config
        from .services import exposure

        verdict = exposure.current_verdict(
            fallback_enabled=bool(_config.OWNER_FALLBACK_ENABLED)
        )
    except Exception:  # noqa: BLE001 - a broken check must not stop the app
        logger.exception("[startup] Could not evaluate network exposure")
    else:
        if verdict.is_dangerous:
            banner = "!" * 72
            logger.critical("\n%s\n  %s\n\n  %s\n%s",
                            banner, verdict.summary, verdict.remedy, banner)
            warnings.append(f"{verdict.summary} {verdict.remedy}")
            if exposure.strict_mode():
                raise RuntimeError(
                    f"Refusing to start: {verdict.summary} {verdict.remedy} "
                    "(SOVEREIGN_STRICT_SECURITY is set.)"
                )
        elif verdict.level == exposure.WARN:
            logger.warning("[startup] %s %s", verdict.summary, verdict.remedy)

    if COPY_BACKEND == "openai" and not OPENAI_API_KEY:
        warnings.append(
            "COPY_BACKEND=openai but OPENAI_API_KEY is not set; copy jobs will "
            "fail until you provide it (or set COPY_BACKEND=mock)."
        )
    if COPY_BACKEND not in _VALID_COPY_BACKENDS:
        warnings.append(
            f"Unknown COPY_BACKEND={COPY_BACKEND!r}; falling back to the mock "
            "copy generator. Valid values: mock, openai, ollama."
        )
    if GENERATOR_BACKEND not in _VALID_IMAGE_BACKENDS:
        warnings.append(
            f"Unknown GENERATOR_BACKEND={GENERATOR_BACKEND!r}; falling back to "
            "the mock image generator. Valid values: mock, comfyui."
        )
    if PRODUCT_SCENE_BACKEND not in _VALID_IMAGE_BACKENDS:
        warnings.append(
            f"Unknown PRODUCT_SCENE_BACKEND={PRODUCT_SCENE_BACKEND!r}; falling "
            "back to the mock product-scene generator. Valid values: mock, comfyui."
        )
    if VIDEO_BACKEND not in _VALID_IMAGE_BACKENDS:
        warnings.append(
            f"Unknown VIDEO_BACKEND={VIDEO_BACKEND!r}; falling back to the mock "
            "video generator. Valid values: mock, comfyui."
        )
    if TRANSCRIPTION_BACKEND != "mock":
        readiness = transcription_readiness()
        if not readiness["available"]:
            warnings.append(
                "ffmpeg is required for real local transcription, and "
                "faster-whisper must be installed in the backend venv."
            )
    if not os.access(STORAGE_DIR, os.W_OK):
        warnings.append(f"Storage directory is not writable: {STORAGE_DIR}")

    for message in warnings:
        logger.warning("[startup] %s", message)
    return warnings
