"""Model Manager inspection helpers.

This is intentionally read-only: it reports configuration, workflow files, and
ComfyUI model/node availability without downloading models or changing defaults.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..config import (
    BASE_DIR,
    COMFYUI_BASE_URL,
    COMFYUI_PRODUCT_SCENE_FLUX_KONTEXT_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_HIDREAM_E1_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_INPAINT_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_IPADAPTER_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_QWEN_IMAGE_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH,
    COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH,
    COMFYUI_VIDEO_ENGINE,
    COMFYUI_VIDEO_MODEL_NAME,
    COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH,
    COMFYUI_VIDEO_UPSCALE_MODEL_NAME,
    COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH,
    COMFYUI_VIDEO_WORKFLOW_PATH,
    COMFYUI_WAN_VIDEO_MODEL_NAME,
    COMFYUI_WAN_VIDEO_WORKFLOW_PATH,
    COMFYUI_WORKFLOW_PATH,
    COPY_BACKEND,
    FLUX1_KREA_MODEL_NAME,
    GENERATOR_BACKEND,
    OLLAMA_COPY_MODEL,
    OPENAI_COPY_MODEL,
    PRODUCT_SCENE_BACKEND,
    PRODUCT_SCENE_MODEL,
    VIDEO_BACKEND,
)
from ..schemas import (
    ComfyUIStatusOut,
    ModelCheckOut,
    ModelManagerStatusOut,
    WorkflowCheckOut,
)

_COMFY_TIMEOUT_SECONDS = 3.0
_U2NET_HUMAN_SEG = "u2net_human_seg.onnx"


@dataclass(frozen=True)
class _ComfySnapshot:
    status: ComfyUIStatusOut
    object_info: dict[str, Any]


def build_model_manager_status() -> ModelManagerStatusOut:
    snapshot = _load_comfy_snapshot()
    workflows = _workflow_checks()
    video_models = _video_models(snapshot.object_info)
    return ModelManagerStatusOut(
        status="ok",
        current_config=_current_config(),
        video_generation_ready=_video_generation_readiness(
            snapshot, video_models, workflows
        ),
        comfyui=snapshot.status,
        image_models=_image_models(snapshot.object_info),
        video_models=video_models,
        copy_models=_copy_models(),
        support_models=_support_models(snapshot.object_info),
        workflows=workflows,
    )


def image_model_checks() -> list[ModelCheckOut]:
    return _image_models(_load_comfy_snapshot().object_info)


def video_model_checks() -> list[ModelCheckOut]:
    return _video_models(_load_comfy_snapshot().object_info)


def workflow_checks() -> list[WorkflowCheckOut]:
    return _workflow_checks()


def _current_config() -> dict[str, str]:
    return {
        "generator_backend": GENERATOR_BACKEND,
        "image_model": _configured_workflow_model(COMFYUI_WORKFLOW_PATH)
        or "mock/default",
        "product_scene_backend": PRODUCT_SCENE_BACKEND,
        "product_scene_model": PRODUCT_SCENE_MODEL or "legacy/default",
        "video_backend": VIDEO_BACKEND,
        "comfyui_video_engine": COMFYUI_VIDEO_ENGINE,
        "copy_backend": COPY_BACKEND,
        "comfyui_base_url": COMFYUI_BASE_URL,
        "comfyui_video_model_name": COMFYUI_VIDEO_MODEL_NAME or "not set",
        "comfyui_wan_video_model_name": COMFYUI_WAN_VIDEO_MODEL_NAME or "not set",
    }


def _video_generation_readiness(
    snapshot: _ComfySnapshot,
    video_models: list[ModelCheckOut],
    workflows: list[WorkflowCheckOut],
) -> str:
    workflow_ready = any(
        workflow.kind == "video"
        and workflow.path.replace("\\", "/").endswith("workflows/image_to_video.json")
        and workflow.exists
        for workflow in workflows
    )
    ltx_ready = any(model.name == "LTX 2.3" and model.installed for model in video_models)
    wan_ready = any(model.name == "Wan 2.2 image-to-video" and model.installed for model in video_models)

    if VIDEO_BACKEND == "mock":
        if snapshot.status.reachable and workflow_ready and ltx_ready:
            return "mock-active; real LTX appears available"
        return "mock-active"
    if VIDEO_BACKEND != "comfyui":
        return f"not-ready; unknown VIDEO_BACKEND={VIDEO_BACKEND}"
    if not snapshot.status.reachable:
        return "not-ready; ComfyUI offline"
    if not workflow_ready:
        return "not-ready; image_to_video workflow missing"
    if COMFYUI_VIDEO_ENGINE == "wan":
        if not wan_ready:
            return "not-ready; Wan model or nodes missing"
        return "real-wan-ready"
    if not ltx_ready:
        return "not-ready; LTX model or nodes missing"
    return "real-ltx-ready"


def _configured_workflow_model(path_value: str) -> str | None:
    path = _workflow_abs(path_value)
    if not path.is_file():
        return None
    try:
        names = _workflow_model_names(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - diagnostic only.
        return None
    return names[0] if names else None


def _load_comfy_snapshot() -> _ComfySnapshot:
    base_url = COMFYUI_BASE_URL.rstrip("/")
    try:
        with httpx.Client(base_url=base_url, timeout=_COMFY_TIMEOUT_SECONDS) as client:
            stats = client.get("/system_stats")
            stats.raise_for_status()
            object_info = client.get("/object_info")
            object_info.raise_for_status()
        stats_json = stats.json()
        version = stats_json.get("system", {}).get("comfyui_version")
        return _ComfySnapshot(
            status=ComfyUIStatusOut(
                base_url=COMFYUI_BASE_URL, reachable=True, version=version
            ),
            object_info=object_info.json(),
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics endpoint should not fail hard.
        return _ComfySnapshot(
            status=ComfyUIStatusOut(
                base_url=COMFYUI_BASE_URL,
                reachable=False,
                error=str(exc),
            ),
            object_info={},
        )


def _image_models(object_info: dict[str, Any]) -> list[ModelCheckOut]:
    checkpoint_options = _loader_options(
        object_info, "CheckpointLoaderSimple", "ckpt_name"
    )
    return [
        _model_check(
            name="Flux Kontext",
            category="image",
            object_info=object_info,
            required_nodes=[
                "FluxKontextImageScale",
                "UNETLoader",
                "DualCLIPLoader",
                "VAELoader",
                "CLIPTextEncodeFlux",
            ],
            required_models=[
                "flux1-dev.safetensors",
                "clip_l.safetensors",
                "t5xxl_fp8_e4m3fn_scaled.safetensors",
                "ae.safetensors",
            ],
            active=PRODUCT_SCENE_MODEL == "flux-kontext",
            source="backend/workflows/product_scene_flux_kontext.json",
        ),
        _model_check(
            name="FLUX.1 Krea Dev",
            category="image",
            object_info=object_info,
            required_nodes=[
                "UNETLoader",
                "DualCLIPLoader",
                "VAELoader",
                "CLIPTextEncode",
                "FluxGuidance",
                "EmptySD3LatentImage",
            ],
            required_models=[
                FLUX1_KREA_MODEL_NAME,
                "clip_l.safetensors",
                "t5xxl_fp8_e4m3fn_scaled.safetensors",
                "ae.safetensors",
            ],
            active=False,
            source="backend/workflows/text_to_image_flux1_krea.json",
        ),
        _model_check(
            name="Qwen Image",
            category="image",
            object_info=object_info,
            required_nodes=[
                "UNETLoader",
                "DualCLIPLoader",
                "VAELoader",
                "TextEncodeQwenImageEdit",
            ],
            required_models=[
                "qwen_image_edit_2509_fp8_e4m3fn.safetensors",
                "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "qwen_image_vae.safetensors",
            ],
            active=PRODUCT_SCENE_MODEL == "qwen-image",
            experimental=True,
            source="backend/workflows/product_scene_qwen_image.json",
        ),
        _model_check(
            name="HiDream E1",
            category="image",
            object_info=object_info,
            required_nodes=[
                "UNETLoader",
                "DualCLIPLoader",
                "VAELoader",
                "CLIPTextEncodeHiDream",
            ],
            required_models=[
                "hidream-e1-full.safetensors",
                "t5xxl_fp8_e4m3fn_scaled.safetensors",
                "llama_3.1_8b_instruct_fp8_scaled.safetensors",
                "ae.safetensors",
            ],
            active=PRODUCT_SCENE_MODEL == "hidream-e1",
            experimental=True,
            source="backend/workflows/product_scene_hidream_e1.json",
        ),
        _checkpoint_family_check(
            "SD 1.5 checkpoints",
            checkpoint_options,
            ["sd15", "sd1.5", "v1-5", "1.5"],
        ),
        _checkpoint_family_check("SDXL checkpoints", checkpoint_options, ["sdxl", "xl"]),
    ]


def _video_models(object_info: dict[str, Any]) -> list[ModelCheckOut]:
    return [
        _model_check(
            name="LTX 2.3",
            category="video",
            object_info=object_info,
            required_nodes=[
                "LTXAVTextEncoderLoader",
                "LoraLoaderModelOnly",
                "LTXVConditioning",
                "LTXVImgToVideo",
                "ModelSamplingLTXV",
                "CreateVideo",
                "SaveVideo",
            ],
            required_models=[
                "ltx-2.3-22b-dev-fp8.safetensors",
                "ltx-2.3-22b-distilled-lora-384.safetensors",
            ],
            active=VIDEO_BACKEND == "comfyui"
            and COMFYUI_VIDEO_MODEL_NAME == "ltx-2.3-22b-dev-fp8.safetensors",
            experimental=True,
            source="backend/workflows/image_to_video.json",
        ),
        _model_check(
            name="LTX 2.3.1",
            category="video",
            object_info=object_info,
            required_nodes=["LTXVImgToVideo", "ModelSamplingLTXV"],
            required_models=["ltx-2.3.1"],
            active=VIDEO_BACKEND == "comfyui" and "2.3.1" in COMFYUI_VIDEO_MODEL_NAME,
            experimental=True,
            source="ComfyUI checkpoint list",
            partial_model_match=True,
        ),
        _model_check(
            name="LTX text encoder",
            category="video",
            object_info=object_info,
            required_nodes=["LTXAVTextEncoderLoader"],
            required_models=["gemma_3_12B_it_fp4_mixed.safetensors"],
            experimental=True,
            source="backend/workflows/image_to_video.json",
        ),
        _model_check(
            name="LTX spatial upscaler",
            category="video",
            object_info=object_info,
            required_nodes=["LatentUpscaleModelLoader"],
            required_models=[COMFYUI_VIDEO_UPSCALE_MODEL_NAME],
            experimental=True,
            source="ComfyUI LatentUpscaleModelLoader",
        ),
        _model_check(
            name="Wan 2.2 image-to-video",
            category="video",
            object_info=object_info,
            required_nodes=[
                "WanImageToVideo",
                "UNETLoader",
                "CLIPLoader",
                "VAELoader",
                "CreateVideo",
                "SaveVideo",
            ],
            required_models=["wan"],
            active=VIDEO_BACKEND == "comfyui" and COMFYUI_VIDEO_ENGINE == "wan",
            experimental=True,
            source="backend/workflows/image_to_video_wan.json",
            partial_model_match=True,
        ),
        _model_check(
            name="Wan text encoder",
            category="video",
            object_info=object_info,
            required_nodes=["CLIPLoader"],
            required_models=["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
            experimental=True,
            source="backend/workflows/image_to_video_wan.json",
        ),
        _model_check(
            name="Wan VAE",
            category="video",
            object_info=object_info,
            required_nodes=["VAELoader"],
            required_models=["wan_2.2_vae.safetensors"],
            experimental=True,
            source="backend/workflows/image_to_video_wan.json",
        ),
    ]


def _copy_models() -> list[ModelCheckOut]:
    return [
        ModelCheckOut(
            name=f"OpenAI copy model: {OPENAI_COPY_MODEL}",
            category="copy",
            installed=COPY_BACKEND == "openai",
            active=COPY_BACKEND == "openai",
            backend="OpenAI",
            source="OPENAI_COPY_MODEL",
            details=["Requires OPENAI_API_KEY at runtime."],
        ),
        ModelCheckOut(
            name=f"Ollama copy model: {OLLAMA_COPY_MODEL}",
            category="copy",
            installed=COPY_BACKEND == "ollama",
            active=COPY_BACKEND == "ollama",
            backend="Ollama",
            source="OLLAMA_COPY_MODEL",
            details=["Local model availability is checked by Ollama in a later phase."],
        ),
        ModelCheckOut(
            name="Mock copy generator",
            category="copy",
            installed=True,
            active=COPY_BACKEND == "mock",
            backend="Mock",
            source="built-in",
            details=["Always available fallback."],
        ),
    ]


def _support_models(object_info: dict[str, Any]) -> list[ModelCheckOut]:
    u2net_path = Path.home() / ".u2net" / _U2NET_HUMAN_SEG
    return [
        ModelCheckOut(
            name="RemBG human segmentation",
            category="support",
            installed=u2net_path.is_file() and "RemBGSession+" in object_info,
            active=True,
            backend="RemBG",
            source=str(u2net_path),
            required_nodes=["RemBGSession+", "ImageRemoveBackground+"],
            required_models=[_U2NET_HUMAN_SEG],
            missing_nodes=[
                node
                for node in ["RemBGSession+", "ImageRemoveBackground+"]
                if node not in object_info
            ],
            missing_models=[] if u2net_path.is_file() else [_U2NET_HUMAN_SEG],
            details=["Used by experimental segmented product-scene workflows."],
        ),
        _model_check(
            name="Flux VAE",
            category="support",
            object_info=object_info,
            required_nodes=["VAELoader"],
            required_models=["ae.safetensors"],
            source="VAELoader",
        ),
        _model_check(
            name="Flux CLIP/T5 encoders",
            category="support",
            object_info=object_info,
            required_nodes=["DualCLIPLoader"],
            required_models=["clip_l.safetensors", "t5xxl_fp8_e4m3fn_scaled.safetensors"],
            source="DualCLIPLoader",
        ),
        ModelCheckOut(
            name="IPAdapter nodes",
            category="support",
            installed=any(name.startswith("IPAdapter") for name in object_info),
            experimental=True,
            backend="ComfyUI",
            source="ComfyUI custom nodes",
            details=["Required only for IPAdapter product-scene mode."],
            missing_nodes=[]
            if any(name.startswith("IPAdapter") for name in object_info)
            else ["IPAdapter*"],
        ),
    ]


def _workflow_checks() -> list[WorkflowCheckOut]:
    active_paths = {
        _workflow_abs(COMFYUI_WORKFLOW_PATH),
        _workflow_abs(COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH),
    }
    active_paths.add(
        _workflow_abs(COMFYUI_WAN_VIDEO_WORKFLOW_PATH)
        if COMFYUI_VIDEO_ENGINE == "wan"
        else _workflow_abs(COMFYUI_VIDEO_WORKFLOW_PATH)
    )
    if PRODUCT_SCENE_MODEL == "flux-kontext":
        active_paths.add(_workflow_abs(COMFYUI_PRODUCT_SCENE_FLUX_KONTEXT_WORKFLOW_PATH))
    elif PRODUCT_SCENE_MODEL == "qwen-image":
        active_paths.add(_workflow_abs(COMFYUI_PRODUCT_SCENE_QWEN_IMAGE_WORKFLOW_PATH))
    elif PRODUCT_SCENE_MODEL == "hidream-e1":
        active_paths.add(_workflow_abs(COMFYUI_PRODUCT_SCENE_HIDREAM_E1_WORKFLOW_PATH))

    configured = [
        ("Text to Image", "image", COMFYUI_WORKFLOW_PATH, False),
        ("Product Scene", "product-scene", COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH, False),
        (
            "Product Scene Flux Kontext",
            "product-scene",
            COMFYUI_PRODUCT_SCENE_FLUX_KONTEXT_WORKFLOW_PATH,
            False,
        ),
        (
            "Product Scene Qwen Image",
            "product-scene",
            COMFYUI_PRODUCT_SCENE_QWEN_IMAGE_WORKFLOW_PATH,
            True,
        ),
        (
            "Product Scene HiDream E1",
            "product-scene",
            COMFYUI_PRODUCT_SCENE_HIDREAM_E1_WORKFLOW_PATH,
            True,
        ),
        (
            "Product Scene IPAdapter",
            "product-scene",
            COMFYUI_PRODUCT_SCENE_IPADAPTER_WORKFLOW_PATH,
            True,
        ),
        (
            "Product Scene Inpaint",
            "product-scene",
            COMFYUI_PRODUCT_SCENE_INPAINT_WORKFLOW_PATH,
            True,
        ),
        ("Image to Video", "video", COMFYUI_VIDEO_WORKFLOW_PATH, True),
        ("Text to Video LTX", "video", COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH, True),
        ("Video to Video LTX", "video", COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH, True),
        ("Video Upscale LTX", "video", COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH, True),
        ("Wan Image to Video", "video", COMFYUI_WAN_VIDEO_WORKFLOW_PATH, True),
    ]
    seen: set[Path] = set()
    checks: list[WorkflowCheckOut] = []
    for name, kind, path_value, experimental in configured:
        path = _workflow_abs(path_value)
        seen.add(path)
        checks.append(_workflow_check(name, kind, path, path in active_paths, experimental))

    for path in sorted((BASE_DIR / "workflows").glob("*.json")):
        if path in seen:
            continue
        checks.append(
            _workflow_check(
                path.stem.replace("_", " ").title(),
                _guess_workflow_kind(path.name),
                path,
                False,
                "experimental" in path.name,
            )
        )
    return checks


def _workflow_check(
    name: str, kind: str, path: Path, active: bool, experimental: bool
) -> WorkflowCheckOut:
    required_models: list[str] = []
    details: list[str] = []
    if path.is_file():
        try:
            workflow = json.loads(path.read_text(encoding="utf-8"))
            required_models = _workflow_model_names(workflow)
            details.append(f"{len(workflow)} nodes")
        except Exception as exc:  # noqa: BLE001 - diagnostic only.
            details.append(f"Could not parse workflow: {exc}")
    return WorkflowCheckOut(
        name=name,
        kind=kind,
        path=str(path.relative_to(BASE_DIR) if path.is_relative_to(BASE_DIR) else path),
        exists=path.is_file(),
        active=active,
        experimental=experimental,
        details=details,
        required_models=required_models,
    )


def _model_check(
    *,
    name: str,
    category: str,
    object_info: dict[str, Any],
    required_nodes: list[str],
    required_models: list[str],
    active: bool = False,
    experimental: bool = False,
    source: str = "",
    partial_model_match: bool = False,
) -> ModelCheckOut:
    missing_nodes = [node for node in required_nodes if node not in object_info]
    missing_models = [
        model
        for model in required_models
        if not _model_available(object_info, model, partial_match=partial_model_match)
    ]
    installed = not missing_nodes and not missing_models
    return ModelCheckOut(
        name=name,
        category=category,
        installed=installed,
        active=active,
        experimental=experimental,
        backend="ComfyUI",
        source=source,
        required_nodes=required_nodes,
        required_models=required_models,
        missing_nodes=missing_nodes,
        missing_models=missing_models,
        details=[] if installed else ["Missing nodes or model files in ComfyUI."],
    )


def _checkpoint_family_check(
    name: str, checkpoint_options: list[str], needles: list[str]
) -> ModelCheckOut:
    matches = [
        option
        for option in checkpoint_options
        if any(needle.lower() in option.lower() for needle in needles)
    ]
    return ModelCheckOut(
        name=name,
        category="image",
        installed=bool(matches),
        active=False,
        backend="ComfyUI",
        source="CheckpointLoaderSimple",
        required_nodes=["CheckpointLoaderSimple"],
        required_models=matches,
        missing_nodes=[] if checkpoint_options else ["CheckpointLoaderSimple"],
        missing_models=[] if matches else [name],
        details=matches[:6],
    )


def _model_available(
    object_info: dict[str, Any], model_name: str, *, partial_match: bool = False
) -> bool:
    for loader, input_name in [
        ("CheckpointLoaderSimple", "ckpt_name"),
        ("UNETLoader", "unet_name"),
        ("CLIPLoader", "clip_name"),
        ("DualCLIPLoader", "clip_name1"),
        ("DualCLIPLoader", "clip_name2"),
        ("VAELoader", "vae_name"),
        ("LTXAVTextEncoderLoader", "text_encoder"),
        ("LTXAVTextEncoderLoader", "ckpt_name"),
        ("LoraLoaderModelOnly", "lora_name"),
        ("LatentUpscaleModelLoader", "model_name"),
    ]:
        for option in _loader_options(object_info, loader, input_name):
            if partial_match:
                if model_name.lower() in option.lower():
                    return True
            elif option == model_name:
                return True
    return False


def _loader_options(
    object_info: dict[str, Any], loader_name: str, input_name: str
) -> list[str]:
    try:
        config = object_info[loader_name]["input"]["required"][input_name]
    except (KeyError, IndexError, TypeError):
        return []
    options: Any = None
    if (
        isinstance(config, list)
        and len(config) > 1
        and isinstance(config[1], dict)
        and isinstance(config[1].get("options"), list)
    ):
        options = config[1]["options"]
    elif isinstance(config, list):
        options = config[0]
    if not isinstance(options, list):
        return []
    return [value for value in options if isinstance(value, str)]


def _workflow_model_names(workflow: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for node in workflow.values():
        inputs = node.get("inputs", {})
        for key in (
            "ckpt_name",
            "unet_name",
            "clip_name",
            "clip_name1",
            "clip_name2",
            "vae_name",
            "text_encoder",
            "lora_name",
            "model_name",
        ):
            value = inputs.get(key)
            if isinstance(value, str) and not value.startswith("__") and value not in names:
                names.append(value)
    return names


def _workflow_abs(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else BASE_DIR / path


def _guess_workflow_kind(filename: str) -> str:
    if "video" in filename:
        return "video"
    if "product_scene" in filename:
        return "product-scene"
    return "image"
