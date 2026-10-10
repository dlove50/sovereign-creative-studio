"""Optional premium provider integrations (admin-only).

Local ComfyUI/LTX/Qwen remain the default engine. Seedance/C-Dance and OpenAI are
optional cloud providers an admin can configure later. API keys are stored ONLY
in the backend secrets folder (never served to the browser, never logged, masked
in the UI, excluded from backups, gitignored). This phase is the configuration
shell for Seedance/OpenAI; HeyGen and ElevenLabs are connected in Cloud Studio.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .. import config

_PROVIDERS = {
    "fal": {
        "name": "fal Motion Studio",
        "kind": "video",
        "note": "Seedance 2.5 character replacement, drafts and 1080p draft completion. Each render uses external provider credits. External API usage may cost money.",
        "defaults": {},
    },
    "heygen": {
        "name": "HeyGen",
        "kind": "video",
        "note": "Use your account's avatar looks and voices through HeyGen. External API usage may cost money.",
        "defaults": {},
    },
    "elevenlabs": {
        "name": "ElevenLabs",
        "kind": "audio",
        "note": "Speech, sound effects, voice changer, transcription, isolation and dubbing. External API usage may cost money.",
        "defaults": {
            "tts_model": "eleven_multilingual_v2",
            "sts_model": "eleven_multilingual_sts_v2",
            "transcription_model": "scribe_v2",
        },
    },
    "seedance": {
        "name": "Seedance / C-Dance 2.0 API",
        "kind": "video",
        "note": "Optional premium cloud video provider. External API usage may cost money.",
        "defaults": {
            "base_url": config.SEEDANCE_DEFAULT_BASE_URL,
            "model_id": config.SEEDANCE_DEFAULT_MODEL_ID,
            "create_endpoint": config.SEEDANCE_DEFAULT_CREATE_ENDPOINT,
            "status_endpoint": config.SEEDANCE_DEFAULT_STATUS_ENDPOINT,
        },
    },
    "openai": {
        "name": "OpenAI API",
        "kind": "ai",
        "note": "Optional premium cloud AI provider for image/artwork/copy and supported media. External API usage may cost money.",
        "defaults": {
            "base_url": config.OPENAI_DEFAULT_BASE_URL,
            "image_model": config.OPENAI_DEFAULT_IMAGE_MODEL,
            "image_size": config.OPENAI_DEFAULT_IMAGE_SIZE,
            "image_quality": config.OPENAI_DEFAULT_IMAGE_QUALITY,
            "organization": "",
            "project": "",
        },
    },
}


def _path() -> Path:
    return config.SECRETS_DIR / "integrations.json"


def _load() -> dict:
    path = _path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a corrupt secrets file must not crash admin.
        return {}


def _save(data: dict) -> None:
    config.SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _mask(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 6:
        return "•" * len(key)
    return f"{key[:3]}{'•' * 6}{key[-2:]}"


def _require_provider(provider: str) -> dict:
    meta = _PROVIDERS.get(provider)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider}'")
    return meta


def list_providers() -> list[dict]:
    """Masked, browser-safe view. Never returns raw API keys."""
    data = _load()
    out = []
    for pid, meta in _PROVIDERS.items():
        entry = data.get(pid, {})
        key = entry.get("api_key")
        meta_defaults = meta.get("defaults", {})
        out.append(
            {
                "id": pid,
                "name": meta["name"],
                "kind": meta["kind"],
                "note": meta["note"],
                "enabled": bool(entry.get("enabled", False)),
                "configured": bool(key),
                "masked_key": _mask(key),
                "last_test_result": entry.get("last_test_result"),
                "config": {
                    k: entry.get(k) or v
                    for k, v in meta_defaults.items()
                },
            }
        )
    return out


def set_key(provider: str, api_key: str) -> list[dict]:
    _require_provider(provider)
    api_key = api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")
    data = _load()
    entry = data.get(provider, {})
    entry["api_key"] = api_key
    data[provider] = entry
    _save(data)
    return list_providers()


def delete_key(provider: str) -> list[dict]:
    _require_provider(provider)
    data = _load()
    if provider in data:
        data[provider].pop("api_key", None)
        data[provider]["enabled"] = False
        data[provider]["last_test_result"] = None
        _save(data)
    return list_providers()


def set_enabled(provider: str, enabled: bool) -> list[dict]:
    _require_provider(provider)
    data = _load()
    entry = data.get(provider, {})
    if enabled and not entry.get("api_key"):
        raise HTTPException(
            status_code=400,
            detail="Configure an API key before enabling this provider.",
        )
    entry["enabled"] = enabled
    data[provider] = entry
    _save(data)
    return list_providers()


def set_config(provider: str, updates: dict[str, str | None]) -> list[dict]:
    meta = _require_provider(provider)
    allowed = set((meta.get("defaults") or {}).keys())
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{provider}' does not expose configurable fields.",
        )
    data = _load()
    entry = data.get(provider, {})
    for key, value in updates.items():
        if key not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported config field: {key}")
        cleaned = (value or "").strip()
        if cleaned:
            entry[key] = cleaned
        else:
            entry.pop(key, None)
    data[provider] = entry
    _save(data)
    return list_providers()


def get_private_provider_config(provider: str) -> dict[str, Any]:
    """Backend-only provider config. Includes raw API key; never return this."""
    meta = _require_provider(provider)
    entry = _load().get(provider, {})
    defaults = meta.get("defaults") or {}
    merged = {key: entry.get(key) or value for key, value in defaults.items()}
    merged.update(
        {
            "enabled": bool(entry.get("enabled", False)),
            "api_key": entry.get("api_key"),
            "configured": bool(entry.get("api_key")),
        }
    )
    return merged


def test_connection(provider: str) -> dict:
    """Placeholder — real connectivity test lands when the provider is wired."""
    _require_provider(provider)
    data = _load()
    entry = data.get(provider, {})
    if not entry.get("api_key"):
        result = "Not configured — add an API key first."
    elif provider in {"heygen", "elevenlabs"}:
        from .cloud_media import connection_test
        result = connection_test(provider, entry["api_key"])
    else:
        result = "Not tested yet — live connection test arrives when this provider is wired."
    entry["last_test_result"] = result
    data[provider] = entry
    _save(data)
    return {"provider": provider, "result": result}
