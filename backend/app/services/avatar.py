"""Avatar animation provider abstraction (Phase 16A foundation, 16C Wan InfiniteTalk).

No local talking-avatar model is wired by default -> "placeholder". For
`comfyui_wan_infinite_talk`, readiness is verified against ComfyUI: reachable, the
`WanInfiniteTalkToVideo` node present, the workflow file present, and the required
model weights installed. Nothing is faked: if anything is missing the UI shows
"Avatar animation model setup required" with the exact missing items and 0 credits
are charged.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from .. import config

WAN_PROVIDER = "comfyui_wan_infinite_talk"
_WAN_NODE = "WanInfiniteTalkToVideo"

# Selected provider -> ComfyUI node(s) that indicate it is installed.
_PROVIDER_NODES = {
    WAN_PROVIDER: [_WAN_NODE],
    "comfyui_liveportrait": ["LivePortraitProcess", "DownloadAndLoadLivePortraitModels"],
    "comfyui_sadtalker": ["SadTalker", "SadTalkerNode"],
    "comfyui_wav2lip": ["Wav2Lip", "Wav2LipNode"],
}


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


def _workflow_path() -> Path:
    path = Path(config.AVATAR_WAN_WORKFLOW_PATH)
    return path if path.is_absolute() else config.BASE_DIR / path


def _wan_missing_models(info: dict) -> list[str]:
    missing: list[str] = []

    audio_encoders = _combo_options(info, "AudioEncoderLoader", "audio_encoder_name")
    want_ae = config.AVATAR_AUDIO_ENCODER_NAME
    if not audio_encoders or (want_ae and want_ae not in audio_encoders):
        missing.append("audio encoder (wav2vec2) in ComfyUI models/audio_encoders")

    unet = _combo_options(info, "UNETLoader", "unet_name")
    want_video = config.AVATAR_WAN_MODEL_NAME
    if want_video:
        if want_video not in unet:
            missing.append(f"Wan video model '{want_video}' in diffusion_models")
    elif not any("wan" in x.lower() for x in unet):
        missing.append("Wan 2.x video diffusion model in diffusion_models (set AVATAR_WAN_MODEL_NAME)")

    patch = _combo_options(info, "ModelPatchLoader", "name")
    want_patch = config.AVATAR_INFINITETALK_PATCH_NAME
    if want_patch:
        if want_patch not in patch:
            missing.append(f"InfiniteTalk model_patch '{want_patch}' in model_patches")
    elif not any("infinitetalk" in x.lower() or "infinite_talk" in x.lower() for x in patch):
        missing.append("InfiniteTalk model_patch in model_patches (set AVATAR_INFINITETALK_PATCH_NAME)")

    if not any("umt5" in x.lower() for x in _combo_options(info, "CLIPLoader", "clip_name")):
        missing.append("Wan umt5 text encoder in text_encoders")

    if not any("wan" in x.lower() for x in _combo_options(info, "VAELoader", "vae_name")):
        missing.append("Wan VAE in vae")

    return missing


def avatar_readiness() -> dict:
    backend = config.AVATAR_BACKEND
    base = {
        "backend": backend,
        "ready": False,
        "comfy_reachable": None,
        "node_present": None,
        "workflow_present": None,
        "models_present": None,
        "missing": [],
        "detail": "",
    }
    if not config.AVATAR_ENABLED:
        return {**base, "detail": "Avatar features are turned off."}
    if backend == "placeholder" or backend not in _PROVIDER_NODES:
        return {
            **base,
            "backend": "placeholder",
            "detail": "Avatar animation model setup required (Wan InfiniteTalk / LivePortrait / SadTalker / Wav2Lip).",
        }

    info = _object_info()
    reachable = info is not None
    base["comfy_reachable"] = reachable
    if not reachable:
        return {**base, "detail": f"ComfyUI is not reachable at {config.COMFYUI_BASE_URL}."}

    node_present = any(n in info for n in _PROVIDER_NODES[backend])
    base["node_present"] = node_present

    if backend == WAN_PROVIDER:
        workflow_present = _workflow_path().is_file()
        missing_models = _wan_missing_models(info)
        base["workflow_present"] = workflow_present
        base["models_present"] = not missing_models

        missing: list[str] = []
        if not node_present:
            missing.append(f"ComfyUI node {_WAN_NODE}")
        if not workflow_present:
            missing.append(f"workflow {config.AVATAR_WAN_WORKFLOW_PATH}")
        missing.extend(missing_models)
        base["missing"] = missing

        if not missing:
            return {**base, "ready": True, "detail": "Wan InfiniteTalk is ready."}
        return {
            **base,
            "detail": "Avatar animation model setup required. Missing: " + "; ".join(missing) + ".",
        }

    # Other ComfyUI providers: node-presence check only (no model wiring yet).
    if node_present:
        return {**base, "ready": True, "detail": f"{backend} nodes detected in ComfyUI."}
    return {**base, "missing": [f"ComfyUI nodes for {backend}"], "detail": f"Required ComfyUI nodes for {backend} not found."}


def avatar_ready() -> bool:
    return avatar_readiness()["ready"]
