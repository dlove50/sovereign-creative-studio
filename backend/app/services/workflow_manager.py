"""Workflow Manager: runtime model / workflow / backend selection.

Lets the UI switch the active image model, product-scene mode, video backend,
and copy backend without editing `.env` or restarting. Selections are validated
against installed models/ComfyUI, applied to the running process, and persisted
to a small JSON file so they survive restarts.

How runtime application works
-----------------------------
Each module that consumes a setting cached its own copy via
`from ..config import X`. To make a change take effect without a restart we
update that attribute on every module that holds it (the same mechanism the test
suite uses via monkeypatch). The target list is explicit and bounded — no magic.

Safety
------
An unavailable selection (offline ComfyUI, missing model, unknown value) is
rejected with a warning and the previous working configuration is kept, so
generation never breaks. Mock backends are always available fallbacks.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import httpx

from .. import config
from . import model_manager

# --- runtime override targets ------------------------------------------------
# config attr -> modules that imported it and must be updated together.
_TARGET_MODULES: dict[str, list[str]] = {
    "PRODUCT_SCENE_MODEL": [
        "app.config",
        "app.product_scene_generators",
        "app.services.model_manager",
    ],
    "COMFYUI_PRODUCT_SCENE_MODE": [
        "app.config",
        "app.product_scene_generators",
    ],
    "COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH": [
        "app.config",
        "app.product_scene_generators",
        "app.services.model_manager",
    ],
    "VIDEO_BACKEND": [
        "app.config",
        "app.video_generators",
        "app.services.model_manager",
        "app.routers.status",
        "app.routers.videos",
    ],
    "COMFYUI_VIDEO_MODEL_NAME": [
        "app.config",
        "app.video_generators",
        "app.services.model_manager",
    ],
    "COMFYUI_VIDEO_ENGINE": [
        "app.config",
        "app.video_generators",
        "app.services.model_manager",
        "app.routers.videos",
    ],
    "COMFYUI_WAN_VIDEO_MODEL_NAME": [
        "app.config",
        "app.video_generators",
        "app.services.model_manager",
    ],
    "COPY_BACKEND": [
        "app.config",
        "app.copy_generators",
        "app.services.model_manager",
        "app.routers.status",
    ],
}

_MANAGED_ATTRS = list(_TARGET_MODULES.keys())

# Logical selection ids.
_IMAGE_MODELS = {
    "flux-kontext": ("Flux Kontext", "Flux Kontext", False),
    "qwen-image": ("Qwen Image", "Qwen Image", True),
    "hidream-e1": ("HiDream E1", "HiDream E1", True),
    "sdxl": ("SDXL", "SDXL checkpoints", False),
    "sd1.5": ("SD1.5", "SD 1.5 checkpoints", False),
}
# id -> (label, experimental). Availability is computed dynamically.
_SCENE_MODES = {
    "img2img": ("Image to Image", False),
    "ipadapter": ("Preserve Subject (IPAdapter)", False),
    "inpaint": ("Inpaint / Background Replace", False),
    "segmented_composite": ("Segmented Composite", True),
    "segmented_composite_polished": ("Segmented Composite (Polished)", True),
    "advertising_scene": ("Advertising Scene", True),
    "fashion_editorial": ("Fashion Editorial", True),
    "creative_fashion_edit": ("Creative Fashion Edit", True),
    "creative_edit": ("Creative Edit (Transform)", True),
    "character_reimagination": ("Character Reimagination", True),
    "fashion_transformation": ("Fashion Transformation", True),
    "cinematic_scene_builder": ("Cinematic Scene Builder", True),
    "clothing_style_edit": ("Clothing & Style Edit", True),
    "pose_edit": ("Pose Edit (SDXL+OpenPose → Qwen)", True),
    "pose_stylized": ("Stylized Pose (SDXL+OpenPose -> Qwen)", True),
    "film_scene": ("Film Scene Keyframe", True),
    "attribute_edit": ("Masked Attribute Edit", True),
}
_VIDEO_MODELS = {
    "mock": ("Mock", None, False),
    "ltx-2.3": ("LTX 2.3", "LTX 2.3", True),
    "ltx-2.3.1": ("LTX 2.3.1", "LTX 2.3.1", True),
    "wan-2.2": ("Wan 2.2 I2V", "Wan 2.2 image-to-video", True),
}
_LTX_23_MODEL_FILE = "ltx-2.3-22b-dev-fp8.safetensors"
_LTX_231_MODEL_FILE = "ltx-2.3.1-distilled.safetensors"
# id -> (label, backend label). Availability is computed dynamically.
_COPY_MODELS = {
    "mock": ("Mock", "Mock"),
    "openai": ("OpenAI", "OpenAI"),
    "claude": ("Claude", "Anthropic"),
    "gemini": ("Gemini", "Google"),
    "ollama": ("Local Ollama", "Ollama"),
    "local-qwen": ("Local Qwen", "Ollama"),
    "local-deepseek": ("Local DeepSeek", "Ollama"),
}

_SELECTABLE_SCENE_MODES = set(_SCENE_MODES)
_SELECTABLE_VIDEO = set(_VIDEO_MODELS)
_SELECTABLE_COPY = set(_COPY_MODELS)


def _persist_path() -> Path:
    return config.STORAGE_DIR / "workflow_config.json"


def _get(attr: str) -> str:
    return getattr(config, attr, "")


def _set(attr: str, value: str) -> None:
    for module_path in _TARGET_MODULES.get(attr, ["app.config"]):
        try:
            module = importlib.import_module(module_path)
        except Exception:  # noqa: BLE001 - a missing optional module is fine.
            continue
        if hasattr(module, attr):
            setattr(module, attr, value)


# --- availability ------------------------------------------------------------
def _comfy_reachable() -> bool:
    try:
        resp = httpx.get(
            f"{config.COMFYUI_BASE_URL.rstrip('/')}/system_stats", timeout=2.0
        )
        resp.raise_for_status()
        return True
    except Exception:  # noqa: BLE001 - reachability probe.
        return False


def _installed_by_name(checks, name: str) -> bool:
    return any(c.name == name and c.installed for c in checks)


def _ollama_model_names() -> list[str] | None:
    """Installed Ollama model names, or None if Ollama is unreachable."""
    try:
        resp = httpx.get(f"{config.OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=2.0)
        resp.raise_for_status()
        return [m.get("name", "") for m in resp.json().get("models", [])]
    except Exception:  # noqa: BLE001 - offline probe.
        return None


def _copy_availability() -> dict[str, tuple[bool, str | None]]:
    """Per-provider (available, reason-if-unavailable)."""
    ollama_models = _ollama_model_names()

    def ollama_has(needle: str) -> bool:
        return ollama_models is not None and any(
            needle in name.lower() for name in ollama_models
        )

    selected_ollama_model = (config.OLLAMA_COPY_MODEL or "").lower()
    ollama_ok = ollama_models is not None and (
        not selected_ollama_model or ollama_has(selected_ollama_model)
    )

    return {
        "mock": (True, None),
        "openai": (
            bool(config.OPENAI_API_KEY),
            None if config.OPENAI_API_KEY else "Set OPENAI_API_KEY",
        ),
        "claude": (
            bool(config.ANTHROPIC_API_KEY),
            None if config.ANTHROPIC_API_KEY else "Set ANTHROPIC_API_KEY",
        ),
        "gemini": (
            bool(config.GEMINI_API_KEY),
            None if config.GEMINI_API_KEY else "Set GEMINI_API_KEY",
        ),
        "ollama": (
            ollama_ok,
            None if ollama_ok else "Ollama offline or selected model not pulled",
        ),
        "local-qwen": (
            ollama_has("qwen"),
            None if ollama_has("qwen") else "No Qwen model pulled in Ollama",
        ),
        "local-deepseek": (
            ollama_has("deepseek"),
            None if ollama_has("deepseek") else "No DeepSeek model pulled in Ollama",
        ),
    }


def _workflow_exists(path_value: str) -> bool:
    path = Path(path_value)
    abs_path = path if path.is_absolute() else config.BASE_DIR / path
    return abs_path.is_file()


def _scene_mode_availability(object_info: dict) -> dict[str, tuple[bool, str | None]]:
    """Per-scene-mode (available, reason-if-unavailable)."""
    support = model_manager._support_models(object_info)  # noqa: SLF001
    ipadapter_ok = any(c.name == "IPAdapter nodes" and c.installed for c in support)
    rembg_ok = any(
        c.name == "RemBG human segmentation" and c.installed for c in support
    )
    # Transform Mode (Path 2) is Qwen-backed; Pose modes add an SDXL+OpenPose
    # first stage. Identity Pose also needs IPAdapter.
    image_checks = model_manager._image_models(object_info)  # noqa: SLF001
    qwen_ok = any(c.name == "Qwen Image" and c.installed for c in image_checks)
    sdxl_ok = any(c.name == "SDXL checkpoints" and c.installed for c in image_checks)
    qwen_reason = (
        None
        if qwen_ok
        else "Qwen not installed — Transform Mode unavailable. Install Qwen Image Edit 2509."
    )
    pose_reason = None
    pose_stylized_reason = None
    if not sdxl_ok:
        pose_reason = "SDXL + OpenPose ControlNet not installed (Pose stage 1)."
    elif not qwen_ok:
        pose_reason = "Qwen not installed — Pose refine stage 2 unavailable."
    pose_stylized_reason = pose_reason
    if pose_reason is None and not ipadapter_ok:
        pose_reason = (
            "IPAdapter not installed - Identity Pose unavailable. Install "
            "ComfyUI_IPAdapter_plus plus SDXL IPAdapter and CLIP Vision models, "
            "or use Stylized Pose fallback."
        )
    # attribute_edit masks: human-parsing (class masks) + GroundingDINO (text).
    seg_ok = "GroundingDinoSAMSegment (segment anything)" in object_info
    parse_ok = "HumanParseMask" in object_info
    if not qwen_ok:
        attr_reason = qwen_reason
    else:
        ready = []
        if parse_ok:
            ready.append("human-parse (pants/hair/face/shoes/garment)")
        if seg_ok:
            ready.append("auto-seg (text prompts)")
        attr_reason = (
            "Ready: " + ", ".join(ready) + "."
            if ready
            else "No auto masking — supply a manual mask."
        )
    seg_workflow = _workflow_exists(
        config.COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_WORKFLOW_PATH
    )
    seg_polished_workflow = _workflow_exists(
        config.COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_POLISHED_WORKFLOW_PATH
    )
    adv_workflow = _workflow_exists(
        config.COMFYUI_PRODUCT_SCENE_ADVERTISING_SCENE_WORKFLOW_PATH
    )
    fashion_workflow = _workflow_exists(
        config.COMFYUI_PRODUCT_SCENE_FASHION_EDITORIAL_WORKFLOW_PATH
    )
    creative_fashion_edit_workflow = _workflow_exists(
        config.COMFYUI_PRODUCT_SCENE_CREATIVE_FASHION_EDIT_WORKFLOW_PATH
    )

    def _seg_reason(workflow_present: bool) -> str | None:
        if not workflow_present:
            return "Segmented-composite workflow file missing"
        if not rembg_ok:
            return "RemBG human segmentation not installed in ComfyUI"
        return None

    return {
        "img2img": (True, None),
        "ipadapter": (
            ipadapter_ok,
            None if ipadapter_ok else "Install ComfyUI_IPAdapter_plus nodes",
        ),
        "inpaint": (True, None),
        "segmented_composite": (bool(seg_workflow and rembg_ok), _seg_reason(seg_workflow)),
        "segmented_composite_polished": (
            bool(seg_polished_workflow and rembg_ok),
            _seg_reason(seg_polished_workflow),
        ),
        "advertising_scene": (
            adv_workflow,
            None if adv_workflow else "Advertising-scene workflow file missing",
        ),
        "fashion_editorial": (
            fashion_workflow,
            None if fashion_workflow else "Fashion-editorial workflow file missing",
        ),
        "creative_fashion_edit": (
            creative_fashion_edit_workflow,
            None
            if creative_fashion_edit_workflow
            else "Creative Fashion Edit workflow file missing",
        ),
        # Transform Mode (Qwen). NOT gated on the Flux workflow — a missing Qwen
        # install reports unavailable instead of silently using Flux.
        "creative_edit": (qwen_ok, qwen_reason),
        "character_reimagination": (qwen_ok, qwen_reason),
        "fashion_transformation": (qwen_ok, qwen_reason),
        "cinematic_scene_builder": (qwen_ok, qwen_reason),
        "clothing_style_edit": (qwen_ok, qwen_reason),
        "film_scene": (qwen_ok, qwen_reason),
        # Identity Pose: SDXL+OpenPose+IPAdapter (stage 1) -> Qwen refine (stage 2).
        "pose_edit": (sdxl_ok and qwen_ok and ipadapter_ok, pose_reason),
        # Stylized Pose fallback: SDXL+OpenPose (stage 1) -> Qwen refine (stage 2).
        "pose_stylized": (sdxl_ok and qwen_ok, pose_stylized_reason),
        # Masked Attribute Editor: available with Qwen; the note reports whether
        # auto-seg (text-prompted masks) is ready or a manual mask is needed.
        "attribute_edit": (qwen_ok, attr_reason),
    }


def _active_copy_model() -> str:
    backend = _get("COPY_BACKEND")
    return {
        "openai": config.OPENAI_COPY_MODEL,
        "claude": config.ANTHROPIC_COPY_MODEL,
        "gemini": config.GEMINI_COPY_MODEL,
        "ollama": config.OLLAMA_COPY_MODEL,
        "local-qwen": config.OLLAMA_QWEN_MODEL,
        "local-deepseek": config.OLLAMA_DEEPSEEK_MODEL,
    }.get(backend, "template")


# --- effective (logical) selections ------------------------------------------
def _effective_image_model() -> str:
    value = _get("PRODUCT_SCENE_MODEL")
    return value if value in _IMAGE_MODELS else "default"


def _effective_video_backend() -> str:
    if _get("VIDEO_BACKEND") != "comfyui":
        return "mock"
    if _get("COMFYUI_VIDEO_ENGINE") == "wan":
        return "wan-2.2"
    return "ltx-2.3.1" if "2.3.1" in _get("COMFYUI_VIDEO_MODEL_NAME") else "ltx-2.3"


def _active_scene_workflow() -> str:
    model = _get("PRODUCT_SCENE_MODEL")
    mapping = {
        "flux-kontext": config.COMFYUI_PRODUCT_SCENE_FLUX_KONTEXT_WORKFLOW_PATH,
        "qwen-image": config.COMFYUI_PRODUCT_SCENE_QWEN_IMAGE_WORKFLOW_PATH,
        "hidream-e1": config.COMFYUI_PRODUCT_SCENE_HIDREAM_E1_WORKFLOW_PATH,
    }
    return mapping.get(model, _get("COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH"))


def get_status() -> dict:
    return {
        "active_image_model": _effective_image_model(),
        "active_scene_workflow": _active_scene_workflow(),
        "active_scene_mode": _get("COMFYUI_PRODUCT_SCENE_MODE"),
        "active_video_backend": _effective_video_backend(),
        "active_copy_backend": _get("COPY_BACKEND"),
        "active_copy_model": _active_copy_model(),
        "generator_backend": _get("GENERATOR_BACKEND"),
        "product_scene_backend": _get("PRODUCT_SCENE_BACKEND"),
        "comfyui_base_url": config.COMFYUI_BASE_URL,
        "comfyui_reachable": _comfy_reachable(),
    }


def get_models() -> dict:
    # One ComfyUI snapshot, reused across all availability checks.
    object_info = model_manager._load_comfy_snapshot().object_info  # noqa: SLF001
    image_checks = model_manager._image_models(object_info)  # noqa: SLF001
    video_checks = model_manager._video_models(object_info)  # noqa: SLF001
    active_image = _effective_image_model()
    active_video = _effective_video_backend()
    active_copy = _get("COPY_BACKEND")

    image_models = [
        {
            "id": option_id,
            "name": label,
            "available": (
                True
                if option_id in {"sdxl", "sd1.5"} and _installed_by_name(image_checks, check_name)
                else _installed_by_name(image_checks, check_name)
            ),
            "active": active_image == option_id,
            "experimental": experimental,
            "backend": "ComfyUI",
            "note": None,
        }
        for option_id, (label, check_name, experimental) in _IMAGE_MODELS.items()
    ]

    scene_availability = _scene_mode_availability(object_info)
    scene_modes = []
    for mode_id, (label, experimental) in _SCENE_MODES.items():
        available, reason = scene_availability[mode_id]
        scene_modes.append(
            {
                "id": mode_id,
                "name": label,
                "available": available,
                "active": _get("COMFYUI_PRODUCT_SCENE_MODE") == mode_id,
                "experimental": experimental,
                "backend": "ComfyUI",
                "note": reason,
            }
        )

    video_models = []
    for option_id, (label, check_name, experimental) in _VIDEO_MODELS.items():
        available = True if check_name is None else _installed_by_name(video_checks, check_name)
        video_models.append(
            {
                "id": option_id,
                "name": label,
                "available": available,
                "active": active_video == option_id,
                "experimental": experimental,
                "backend": "Mock"
                if option_id == "mock"
                else ("ComfyUI/Wan" if option_id.startswith("wan") else "ComfyUI/LTX"),
                "note": None,
            }
        )

    copy_availability = _copy_availability()
    copy_models = []
    for option_id, (label, backend) in _COPY_MODELS.items():
        available, reason = copy_availability[option_id]
        copy_models.append(
            {
                "id": option_id,
                "name": label,
                "available": available,
                "active": active_copy == option_id,
                "experimental": False,
                "backend": backend,
                "note": reason,
            }
        )

    return {
        "image_models": image_models,
        "scene_modes": scene_modes,
        "video_models": video_models,
        "copy_models": copy_models,
    }


def get_workflows():
    return model_manager.workflow_checks()


# --- updates -----------------------------------------------------------------
def _apply_image_model(value: str) -> tuple[bool, str | None]:
    if value not in _IMAGE_MODELS and value != "default":
        return False, f"Unknown image model '{value}'."
    if value in _IMAGE_MODELS:
        _, check_name, _ = _IMAGE_MODELS[value]
        if not _installed_by_name(model_manager.image_model_checks(), check_name):
            return False, f"Image model '{value}' is not installed; keeping previous."
    # sdxl / sd1.5 use the legacy SD workflow (PRODUCT_SCENE_MODEL empty).
    config_value = value if value in {"flux-kontext", "qwen-image", "hidream-e1"} else ""
    _set("PRODUCT_SCENE_MODEL", config_value)
    return True, None


def _apply_scene_mode(value: str) -> tuple[bool, str | None]:
    if value not in _SCENE_MODES:
        return False, f"Unknown scene mode '{value}'."
    object_info = model_manager._load_comfy_snapshot().object_info  # noqa: SLF001
    available, reason = _scene_mode_availability(object_info)[value]
    if not available:
        return False, f"Scene mode '{value}' is unavailable: {reason}. Keeping previous."
    _set("COMFYUI_PRODUCT_SCENE_MODE", value)
    return True, None


def _apply_scene_workflow(value: str) -> tuple[bool, str | None]:
    path = Path(value)
    abs_path = path if path.is_absolute() else config.BASE_DIR / path
    if not abs_path.is_file():
        return False, f"Workflow file not found: {value}"
    _set("COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH", value)
    return True, None


def _apply_video_backend(value: str) -> tuple[bool, str | None]:
    if value not in _SELECTABLE_VIDEO:
        return False, f"Unknown video backend '{value}'."
    if value == "mock":
        _set("VIDEO_BACKEND", "mock")
        return True, None
    _, check_name, _ = _VIDEO_MODELS[value]
    object_info = model_manager._load_comfy_snapshot().object_info  # noqa: SLF001
    if not _installed_by_name(model_manager._video_models(object_info), check_name):  # noqa: SLF001
        return False, f"{check_name} is not available (ComfyUI offline or model missing); keeping previous."
    _set("VIDEO_BACKEND", "comfyui")
    if value == "wan-2.2":
        _set("COMFYUI_VIDEO_ENGINE", "wan")
        wan_model = next(
            (
                option
                for option in model_manager._loader_options(  # noqa: SLF001
                    object_info, "UNETLoader", "unet_name"
                )
                if "wan" in option.lower()
            ),
            "",
        )
        if wan_model:
            _set("COMFYUI_WAN_VIDEO_MODEL_NAME", wan_model)
        return True, None
    _set("COMFYUI_VIDEO_ENGINE", "ltx")
    _set(
        "COMFYUI_VIDEO_MODEL_NAME",
        _LTX_231_MODEL_FILE if value == "ltx-2.3.1" else _LTX_23_MODEL_FILE,
    )
    return True, None


def _apply_copy_backend(value: str) -> tuple[bool, str | None]:
    if value not in _SELECTABLE_COPY:
        return False, f"Unknown copy backend '{value}'."
    available, reason = _copy_availability()[value]
    if not available:
        return False, f"Copy provider '{value}' is unavailable: {reason}. Keeping previous."
    _set("COPY_BACKEND", value)
    return True, None


_FIELD_APPLIERS = {
    "image_model": _apply_image_model,
    "scene_mode": _apply_scene_mode,
    "scene_workflow": _apply_scene_workflow,
    "video_backend": _apply_video_backend,
    "copy_backend": _apply_copy_backend,
}


def update_config(changes: dict, *, persist: bool = True) -> dict:
    applied: dict[str, str] = {}
    warnings: list[str] = []
    for field, value in changes.items():
        if value is None:
            continue
        applier = _FIELD_APPLIERS.get(field)
        if applier is None:
            warnings.append(f"Unknown setting '{field}'.")
            continue
        ok, warning = applier(value)
        if ok:
            applied[field] = value
        if warning:
            warnings.append(warning)
    if persist:
        _persist()
    return {"applied": applied, "warnings": warnings, "status": get_status()}


def _persist() -> None:
    selection = {
        "image_model": _effective_image_model(),
        "scene_mode": _get("COMFYUI_PRODUCT_SCENE_MODE"),
        "scene_workflow": _get("COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH"),
        "video_backend": _effective_video_backend(),
        "copy_backend": _get("COPY_BACKEND"),
    }
    try:
        config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        _persist_path().write_text(json.dumps(selection, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - persistence is best-effort.
        pass


def load_persisted_and_apply() -> None:
    """Apply persisted selections on startup. Unavailable ones are skipped
    (validated), so a stale or now-offline choice falls back safely."""
    path = _persist_path()
    if not path.is_file():
        return
    try:
        selection = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    update_config(selection, persist=False)


# --- test support ------------------------------------------------------------
def export_runtime() -> dict[str, str]:
    """Snapshot the managed runtime values (for tests to restore)."""
    return {attr: _get(attr) for attr in _MANAGED_ATTRS}


def import_runtime(values: dict[str, str]) -> None:
    for attr, value in values.items():
        _set(attr, value)
