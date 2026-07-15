"""Local text-to-image quality presets.

The default (`local_fast`) keeps the current safe local model. Higher-quality
presets are verified against the installed ComfyUI models; missing models report
"setup required" (never faked). FLUX.2 Klein 4B is the recommended quality target
once its weights are installed; FLUX.2-dev (32B) is intentionally not offered
because it is too heavy for this machine (16 GB VRAM / 32 GB RAM).
"""
from __future__ import annotations

from pathlib import Path

import httpx

from .. import config

DEFAULT_PRESET = "local_fast"


def _workflow(rel: str) -> Path:
    path = Path(rel)
    return path if path.is_absolute() else config.BASE_DIR / path


# Each preset declares the ComfyUI loader options that must contain a matching
# model for the preset to be runnable. `local_fast` is always available (it is the
# safe current default / mock fallback).
_PRESETS = [
    {
        "id": "local_fast",
        "label": "Local Fast / Current",
        "description": "Current fast local model. Safe default; quickest to render.",
        "workflow": config.COMFYUI_WORKFLOW_PATH,
        "recommended": False,
        "is_default": True,
        "always_available": True,
        "checks": [],
    },
    {
        "id": "flux2_klein",
        "label": "FLUX.2 Klein 4B",
        "description": "Recommended quality. Best for realistic subjects and animal faces. Needs the FLUX.2 Klein 4B weights.",
        "workflow": config.IMAGE_WORKFLOW_FLUX2_KLEIN,
        "recommended": True,
        "is_default": False,
        "always_available": False,
        "checks": [
            ("UNETLoader", "unet_name", [config.FLUX2_KLEIN_MODEL_NAME] if config.FLUX2_KLEIN_MODEL_NAME else ["flux.2", "flux2", "klein"],
             "FLUX.2 Klein 4B model in ComfyUI diffusion_models (set FLUX2_KLEIN_MODEL_NAME)"),
            ("CLIPLoader", "clip_name", ["qwen_3_4b.safetensors", "qwen_3_4b"], "Qwen3-4B text encoder (qwen_3_4b.safetensors) in text_encoders"),
            ("VAELoader", "vae_name", ["flux2-vae"], "FLUX.2 VAE (flux2-vae.safetensors) in vae"),
        ],
    },
    {
        "id": "flux1_krea",
        "label": "FLUX.1 Krea Dev",
        "description": "Photographic FLUX.1 Krea Dev FP8. Optional realism upgrade; not the default.",
        "workflow": config.IMAGE_WORKFLOW_FLUX1_KREA,
        "recommended": False,
        "is_default": False,
        "always_available": False,
        "checks": [
            (
                "UNETLoader",
                "unet_name",
                [config.FLUX1_KREA_MODEL_NAME],
                "FLUX.1 Krea Dev FP8 model in diffusion_models",
            ),
            ("DualCLIPLoader", "clip_name1", ["clip_l.safetensors"], "Flux CLIP-L text encoder"),
            (
                "DualCLIPLoader",
                "clip_name2",
                ["t5xxl_fp8_e4m3fn_scaled.safetensors", "t5xxl_fp16.safetensors"],
                "Flux T5 text encoder",
            ),
            ("VAELoader", "vae_name", ["ae.safetensors"], "FLUX VAE (ae.safetensors) in vae"),
        ],
    },
    {
        "id": "krea2_turbo_fp8",
        "label": "Krea 2 Turbo FP8 — Local",
        "description": "Krea 2 Turbo FP8 local model. Photorealistic, fast. Uses Qwen3-VL-4B text encoder and Krea VAE.",
        "workflow": config.IMAGE_WORKFLOW_KREA2_TURBO,
        "recommended": False,
        "is_default": False,
        "always_available": False,
        "checks": [
            (
                "UNETLoader",
                "unet_name",
                [config.KREA2_TURBO_MODEL_NAME],
                "Krea 2 Turbo FP8 model (krea2_turbo_fp8_scaled.safetensors) in diffusion_models",
            ),
            (
                "CLIPLoader",
                "clip_name",
                [config.KREA2_TEXT_ENCODER_NAME, "qwen3vl"],
                "Krea 2 text encoder (qwen3vl_4b_fp8_scaled.safetensors) in text_encoders",
            ),
            (
                "VAELoader",
                "vae_name",
                [config.KREA2_VAE_NAME, "qwen_image_vae"],
                "Krea 2 VAE (qwen_image_vae.safetensors) in vae",
            ),
        ],
    },
    {
        "id": "flux1_dev",
        "label": "FLUX.1-dev",
        "description": "High-quality FLUX.1-dev (FP8). Strong realism; heavier than the fast model.",
        "workflow": config.IMAGE_WORKFLOW_FLUX1_DEV,
        "recommended": False,
        "is_default": False,
        "always_available": False,
        "checks": [
            ("UNETLoader", "unet_name", ["flux1-dev", "flux1_dev"], "FLUX.1-dev model in diffusion_models"),
            ("VAELoader", "vae_name", ["ae."], "FLUX VAE (ae.safetensors) in vae"),
        ],
    },
    {
        "id": "sdxl",
        "label": "SDXL Base + Refiner",
        "description": "SDXL fallback. Solid general quality (refiner optional if installed).",
        "workflow": config.IMAGE_WORKFLOW_SDXL,
        "recommended": False,
        "is_default": False,
        "always_available": False,
        "checks": [
            ("CheckpointLoaderSimple", "ckpt_name", ["sd_xl_base", "sdxl"], "SDXL base checkpoint in checkpoints"),
        ],
    },
    {
        "id": "illustrious_xl",
        "label": "Illustrious XL (anime)",
        "description": "Dedicated anime/illustration SDXL checkpoint. Best for anime when installed.",
        "workflow": config.IMAGE_WORKFLOW_ILLUSTRIOUS,
        "recommended": False,
        "is_default": False,
        "always_available": False,
        "checks": [
            ("CheckpointLoaderSimple", "ckpt_name", ["illustrious", "noobai", "pony"],
             "an anime SDXL checkpoint (e.g. Illustrious XL) in checkpoints"),
        ],
    },
    {
        "id": "z_image_turbo",
        "label": "Z-Image Turbo",
        "description": "Tongyi Z-Image Turbo. Fast (8 steps), strong realism and text rendering.",
        "workflow": config.IMAGE_WORKFLOW_Z_IMAGE_TURBO,
        "recommended": False,
        "is_default": False,
        "always_available": False,
        "checks": [
            ("UNETLoader", "unet_name", ["z_image_turbo"], "Z-Image Turbo model (z_image_turbo_bf16.safetensors) in diffusion_models"),
            ("CLIPLoader", "clip_name", ["qwen_3_4b"], "Qwen3-4B text encoder (qwen_3_4b.safetensors) in text_encoders"),
            ("VAELoader", "vae_name", ["ae.safetensors"], "FLUX VAE (ae.safetensors) in vae"),
        ],
    },
    {
        "id": "netayume_anime",
        "label": "NetaYume Lumina (anime)",
        "description": "NetaYume v3.5 anime model (Lumina 2). High-quality anime and illustration style.",
        "workflow": config.IMAGE_WORKFLOW_NETAYUME,
        "recommended": False,
        "is_default": False,
        "always_available": False,
        "checks": [
            ("CheckpointLoaderSimple", "ckpt_name", ["netayume"],
             "NetaYume Lumina checkpoint (NetaYumev35_pretrained_all_in_one.safetensors) in checkpoints"),
        ],
    },
]

_PRESET_BY_ID = {p["id"]: p for p in _PRESETS}


def _object_info() -> dict | None:
    try:
        resp = httpx.get(f"{config.COMFYUI_BASE_URL.rstrip('/')}/object_info", timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001 - reachability probe.
        return None


def _combo_options(info: dict, node: str, field: str) -> list[str]:
    try:
        spec = info[node]["input"]["required"][field]
        if isinstance(spec, list) and spec and spec[0] == "COMBO" and isinstance(spec[1], dict):
            return [str(x) for x in spec[1].get("options", [])]
        values = spec[0] if isinstance(spec, list) and spec else []
        return [str(x) for x in values] if isinstance(values, list) else []
    except Exception:  # noqa: BLE001
        return []


def is_known_preset(preset_id: str | None) -> bool:
    return bool(preset_id) and preset_id in _PRESET_BY_ID


def workflow_for_preset(preset_id: str | None) -> Path:
    preset = _PRESET_BY_ID.get(preset_id or DEFAULT_PRESET, _PRESET_BY_ID[DEFAULT_PRESET])
    path = _workflow(preset["workflow"])
    return path if path.is_file() else _workflow(config.COMFYUI_WORKFLOW_PATH)


def _preset_missing(preset: dict, info: dict | None) -> list[str]:
    if preset.get("always_available"):
        return []
    if info is None:
        return ["ComfyUI is not reachable"]
    missing: list[str] = []
    if not _workflow(preset["workflow"]).is_file():
        missing.append(f"workflow {preset['workflow']}")
    for node, field, needles, label in preset["checks"]:
        options = [o.lower() for o in _combo_options(info, node, field)]
        if not any(any(n.lower() in o for o in options) for n in needles):
            missing.append(label)
    return missing


def preset_ready(preset_id: str | None) -> bool:
    preset = _PRESET_BY_ID.get(preset_id or DEFAULT_PRESET)
    if preset is None:
        return False
    if preset.get("always_available"):
        return True
    return not _preset_missing(preset, _object_info())


def list_image_presets() -> list[dict]:
    info = _object_info()
    out: list[dict] = []
    for preset in _PRESETS:
        missing = _preset_missing(preset, info)
        ready = not missing
        detail = "Ready." if ready else "Model setup required. Missing: " + "; ".join(missing) + "."
        out.append(
            {
                "id": preset["id"],
                "label": preset["label"],
                "description": preset["description"],
                "recommended": preset["recommended"],
                "is_default": preset["is_default"],
                "ready": ready,
                "missing": missing,
                "detail": "Ready." if ready else detail,
            }
        )
    return out
