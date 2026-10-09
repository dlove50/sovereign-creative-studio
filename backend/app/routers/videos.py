import json
from pathlib import Path
import shutil
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import (
    BASE_DIR,
    CREDITS_PER_H3_VIDEO,
    CREDITS_PER_SEEDANCE_VIDEO,
    COMFYUI_BASE_URL,
    CREDITS_PER_VIDEO,
    COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH,
    COMFYUI_VIDEO_ENGINE,
    COMFYUI_VIDEO_EXTENSION_WORKFLOW_PATH,
    COMFYUI_VIDEO_MODEL_NAME,
    COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH,
    COMFYUI_VIDEO_UPSCALE_MODEL_NAME,
    COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH,
    COMFYUI_WAN_VIDEO_MODEL_NAME,
    COMFYUI_WAN_VIDEO_WORKFLOW_PATH,
    H3_AUDIO_VAE_NAME,
    H3_CONTROLNET_NAME,
    H3_TEXT_ENCODER_NAME,
    H3_TURBO_LORA_NAME,
    H3_UNET_NAME,
    H3_VIDEO_VAE_NAME,
    VIDEO_BACKEND,
)
from ..database import get_db
from ..deps import get_current_user
from ..models import ProductSceneGeneration, Project, User, VideoGeneration
from ..schemas import VideoCreate, VideoModeOption, VideoOut, VideoProviderReadiness
from ..services import trash
from ..services.briefs import load_project_brief, with_brief_context
from ..services.integrations import get_private_provider_config
from ..services.source_validation import validate_source_media_url
from ..services.video_jobs import enqueue_video

router = APIRouter(prefix="/api/videos", tags=["videos"])
_COMFY_TIMEOUT_SECONDS = 3.0
_TEXT_TO_VIDEO_REQUIRED_NODES = {
    "CheckpointLoaderSimple",
    "LoraLoaderModelOnly",
    "LTXAVTextEncoderLoader",
    "CLIPTextEncode",
    "LTXVConditioning",
    "EmptyLTXVLatentVideo",
    "ModelSamplingLTXV",
    "KSampler",
    "VAEDecodeTiled",
    "CreateVideo",
    "SaveVideo",
}
_TEXT_ENCODER_MODEL = "gemma_3_12B_it_fp4_mixed.safetensors"
_LTX_DISTILLED_LORA_MODEL = "ltx-2.3-22b-distilled-lora-384.safetensors"
_VIDEO_UPSCALE_REQUIRED_NODES = {
    "CheckpointLoaderSimple",
    "LoadVideo",
    "GetVideoComponents",
    "VAEEncodeTiled",
    "LatentUpscaleModelLoader",
    "LTXVLatentUpsampler",
    "VAEDecodeTiled",
    "CreateVideo",
    "SaveVideo",
}
_VIDEO_TO_VIDEO_REQUIRED_NODES = {
    "CheckpointLoaderSimple",
    "LoadVideo",
    "GetVideoComponents",
    "LTXAVTextEncoderLoader",
    "CLIPTextEncode",
    "LTXVConditioning",
    "VAEEncodeTiled",
    "ModelSamplingLTXV",
    "KSampler",
    "VAEDecodeTiled",
    "CreateVideo",
    "SaveVideo",
}
_VIDEO_EXTENSION_REQUIRED_NODES = {
    "CheckpointLoaderSimple",
    "LoadVideo",
    "GetVideoComponents",
    "ImageFromBatch",
    "ImageScale",
    "LTXAVTextEncoderLoader",
    "CLIPTextEncode",
    "LTXVConditioning",
    "EmptyLTXVLatentVideo",
    "LTXVAddGuide",
    "ModelSamplingLTXV",
    "KSampler",
    "LTXVCropGuides",
    "VAEDecodeTiled",
    "CreateVideo",
    "SaveVideo",
}

# Video Studio mode registry (Phase C11). id -> (label, description, source_required).
_VIDEO_MODES = [
    ("image_to_video", "Image → Video", "Animate a completed product scene or image.", True),
    ("text_to_video", "Text → Video", "Generate a clip from a text prompt only.", False),
    ("video_to_video", "Video → Video", "Restyle or enhance an existing clip/image.", True),
    ("video_extension", "Video Extension", "Continue / extend a clip's duration.", True),
    ("video_upscale", "Video Upscale", "Render a higher-resolution version.", True),
]


@router.get("/modes", response_model=list[VideoModeOption])
def list_video_modes():
    # Mock renders placeholders for every mode. Real ComfyUI modes become
    # available only after a dedicated workflow + node/model check passes.
    is_mock = VIDEO_BACKEND == "mock"
    backend_label = (
        "Mock"
        if is_mock
        else ("ComfyUI/Wan" if COMFYUI_VIDEO_ENGINE == "wan" else "ComfyUI/LTX")
    )
    text_ready, text_note = _text_to_video_ready()
    upscale_ready, upscale_note = _video_upscale_ready()
    v2v_ready, v2v_note = _video_to_video_ready()
    ext_ready, ext_note = _video_extension_ready()
    seedance_ready, seedance_note = _seedance_ready()
    wan_ready, wan_note = _wan_ready()
    h3_ready, h3_note = _h3_ready()
    h3_control_ready, h3_control_note = _h3_controlnet_ready()
    options = []
    for mode_id, label, description, source_required in _VIDEO_MODES:
        if is_mock:
            available = True
            note = None
        elif mode_id == "image_to_video":
            available = True
            note = None
        elif mode_id == "text_to_video":
            available = text_ready
            note = None if available else text_note
        elif mode_id == "video_upscale":
            available = upscale_ready
            note = None if available else upscale_note
        elif mode_id == "video_to_video":
            available = v2v_ready
            note = None if available else v2v_note
        elif mode_id == "video_extension":
            available = ext_ready
            note = None if available else ext_note
        else:
            available = False
            note = (
                "Not wired yet. Planned mode; requires a dedicated ComfyUI "
                "workflow setup before it can run here."
            )
        options.append(
            VideoModeOption(
                id=mode_id,
                name=label,
                description=description,
                source_required=source_required,
                available=available,
                backend=backend_label,
                note=note,
                providers={
                    "local_ltx": VideoProviderReadiness(
                        available=available,
                        cost=CREDITS_PER_VIDEO,
                        note=note,
                    ),
                    "local_wan": VideoProviderReadiness(
                        available=wan_ready and mode_id == "image_to_video",
                        cost=CREDITS_PER_VIDEO,
                        note=(
                            wan_note
                            if not wan_ready
                            else (
                                None
                                if mode_id == "image_to_video"
                                else "Wan 2.1 is only wired for Image -> Video."
                            )
                        ),
                    ),
                    "local_h3": VideoProviderReadiness(
                        available=(
                            h3_control_ready if mode_id == "video_to_video"
                            else h3_ready and mode_id in {"text_to_video", "image_to_video"}
                        ),
                        cost=CREDITS_PER_H3_VIDEO,
                        note=(
                            (h3_control_note if mode_id == "video_to_video" else h3_note)
                            if not (h3_control_ready if mode_id == "video_to_video" else h3_ready)
                            else (
                                None
                                if mode_id in {"text_to_video", "image_to_video", "video_to_video"}
                                else "MiniMax H3 makes video with sound from text, an image or a guide video."
                            )
                        ),
                    ),
                    "seedance_api": VideoProviderReadiness(
                        available=seedance_ready and mode_id in {"text_to_video", "image_to_video"},
                        cost=CREDITS_PER_SEEDANCE_VIDEO,
                        note=(
                            seedance_note
                            if not seedance_ready
                            else (
                                None
                                if mode_id in {"text_to_video", "image_to_video"}
                                else "Seedance is only wired for Text -> Video and Image -> Video in Phase 14A."
                            )
                        ),
                    ),
                },
            )
        )
    return options


def _seedance_ready() -> tuple[bool, str | None]:
    cfg = get_private_provider_config("seedance")
    if not cfg.get("enabled") or not cfg.get("api_key"):
        return False, "Seedance provider is not configured. Admin setup required."
    if not cfg.get("base_url"):
        return False, "Seedance provider base URL is missing. Admin setup required."
    return True, None


_WAN_REQUIRED_NODES = {
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "LoadImage",
    "CLIPTextEncode",
    "WanImageToVideo",
    "KSampler",
    "VAEDecode",
    "CreateVideo",
    "SaveVideo",
}
_WAN_TEXT_ENCODER_MODEL = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
_WAN_VAE_MODEL = "wan_2.1_vae.safetensors"


def _wan_ready() -> tuple[bool, str | None]:
    if VIDEO_BACKEND == "mock":
        return True, None
    if VIDEO_BACKEND != "comfyui":
        return False, f"Video backend {VIDEO_BACKEND} is not a real ComfyUI backend."

    workflow_path = _workflow_path(COMFYUI_WAN_VIDEO_WORKFLOW_PATH)
    if not workflow_path.is_file():
        return False, f"Wan Image -> Video workflow missing: {workflow_path}"

    try:
        with httpx.Client(
            base_url=COMFYUI_BASE_URL.rstrip("/"),
            timeout=_COMFY_TIMEOUT_SECONDS,
        ) as client:
            response = client.get("/object_info")
            response.raise_for_status()
            object_info = response.json()
    except Exception as exc:  # noqa: BLE001 - readiness should degrade to unavailable.
        return False, f"ComfyUI unavailable at {COMFYUI_BASE_URL}: {exc}"

    missing_nodes = sorted(
        node for node in _WAN_REQUIRED_NODES if node not in object_info
    )
    if missing_nodes:
        return False, "Missing ComfyUI nodes: " + ", ".join(missing_nodes)

    unet_options = _loader_options(object_info, "UNETLoader", "unet_name")
    if COMFYUI_WAN_VIDEO_MODEL_NAME not in unet_options:
        return False, f"Wan model not listed in ComfyUI: {COMFYUI_WAN_VIDEO_MODEL_NAME}"
    clip_options = _loader_options(object_info, "CLIPLoader", "clip_name")
    if _WAN_TEXT_ENCODER_MODEL not in clip_options:
        return False, f"Wan text encoder not listed in ComfyUI: {_WAN_TEXT_ENCODER_MODEL}"
    vae_options = _loader_options(object_info, "VAELoader", "vae_name")
    if _WAN_VAE_MODEL not in vae_options:
        return False, f"Wan VAE not listed in ComfyUI: {_WAN_VAE_MODEL}"

    return True, None


_H3_REQUIRED_NODES = (
    "MiniMaxH3ImageToVideo", "UNETLoader", "CLIPLoader", "VAELoader", "VAEDecodeAudio",
    "LoraLoaderModelOnly", "BasicGuider", "SamplerCustomAdvanced", "CreateVideo", "SaveVideo",
)


def _h3_ready() -> tuple[bool, str | None]:
    """MiniMax H3 needs ComfyUI's native H3 nodes plus its model files."""
    if VIDEO_BACKEND == "mock":
        return True, None
    if VIDEO_BACKEND != "comfyui":
        return False, f"Video backend {VIDEO_BACKEND} is not a real ComfyUI backend."
    try:
        with httpx.Client(base_url=COMFYUI_BASE_URL.rstrip("/"), timeout=_COMFY_TIMEOUT_SECONDS) as client:
            response = client.get("/object_info")
            response.raise_for_status()
            object_info = response.json()
    except Exception as exc:  # noqa: BLE001 - readiness should degrade to unavailable.
        return False, f"ComfyUI unavailable at {COMFYUI_BASE_URL}: {exc}"
    missing_nodes = sorted(node for node in _H3_REQUIRED_NODES if node not in object_info)
    if missing_nodes:
        return False, "Update ComfyUI: missing nodes " + ", ".join(missing_nodes)
    wanted = (
        ("UNETLoader", "unet_name", H3_UNET_NAME, "model"),
        ("CLIPLoader", "clip_name", H3_TEXT_ENCODER_NAME, "text encoder"),
        ("VAELoader", "vae_name", H3_VIDEO_VAE_NAME, "video VAE"),
        ("VAELoader", "vae_name", H3_AUDIO_VAE_NAME, "audio VAE"),
        ("LoraLoaderModelOnly", "lora_name", H3_TURBO_LORA_NAME, "turbo LoRA"),
    )
    still_downloading = [
        label for loader, field, name, label in wanted
        if name not in _loader_options(object_info, loader, field)
    ]
    if still_downloading:
        return False, "MiniMax H3 files not in ComfyUI yet: " + ", ".join(still_downloading)
    return True, None


_H3_CONTROL_NODES = ("MiniMaxH3FunControlNetApply", "ModelPatchLoader", "Canny", "LoadVideo", "GetVideoComponents")


def _h3_controlnet_ready() -> tuple[bool, str | None]:
    """Video -> Video on H3 needs the Fun ControlNet file and a few ComfyUI nodes."""
    ready, note = _h3_ready()
    if not ready:
        return False, note
    if VIDEO_BACKEND == "mock":
        return True, None
    try:
        with httpx.Client(base_url=COMFYUI_BASE_URL.rstrip("/"), timeout=_COMFY_TIMEOUT_SECONDS) as client:
            object_info = client.get("/object_info").json()
    except Exception as exc:  # noqa: BLE001
        return False, f"ComfyUI unavailable at {COMFYUI_BASE_URL}: {exc}"
    missing = [n for n in _H3_CONTROL_NODES if n not in object_info]
    if missing:
        return False, "Update ComfyUI: missing nodes " + ", ".join(missing)
    if H3_CONTROLNET_NAME not in _loader_options(object_info, "ModelPatchLoader", "name"):
        return False, "MiniMax H3 ControlNet file not in ComfyUI yet."
    return True, None


def _provider_cost(provider: str) -> int:
    if provider == "seedance_api":
        return CREDITS_PER_SEEDANCE_VIDEO
    return CREDITS_PER_H3_VIDEO if provider == "local_h3" else CREDITS_PER_VIDEO


def _workflow_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else BASE_DIR / path


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
    return [option for option in options if isinstance(option, str)]


_WORKFLOW_MODEL_INPUTS = {
    "CheckpointLoaderSimple": "ckpt_name",
    "UNETLoader": "unet_name",
    "CLIPLoader": "clip_name",
    "VAELoader": "vae_name",
    "LoraLoaderModelOnly": "lora_name",
}


def _workflow_models_ready(
    workflow_text: str, object_info: dict[str, Any]
) -> tuple[bool, str | None]:
    """Readiness for an arbitrary ComfyUI API workflow: its nodes exist and every
    model file it names is listed by the running ComfyUI."""
    try:
        workflow = json.loads(workflow_text)
    except ValueError as exc:
        return False, f"Text -> Video workflow is not valid JSON: {exc}"
    nodes = [
        node for node in workflow.values() if isinstance(node, dict) and "class_type" in node
    ]
    missing_nodes = sorted({n["class_type"] for n in nodes if n["class_type"] not in object_info})
    if missing_nodes:
        return False, "Missing ComfyUI nodes: " + ", ".join(missing_nodes)
    for node in nodes:
        input_name = _WORKFLOW_MODEL_INPUTS.get(node["class_type"])
        value = (node.get("inputs") or {}).get(input_name) if input_name else None
        if isinstance(value, str) and value and not value.startswith("__"):
            if value not in _loader_options(object_info, node["class_type"], input_name):
                return False, f"Model not listed in ComfyUI: {value}"
    return True, None


def _text_to_video_ready() -> tuple[bool, str | None]:
    if VIDEO_BACKEND == "mock":
        return True, None
    if VIDEO_BACKEND != "comfyui":
        return False, f"Video backend {VIDEO_BACKEND} is not a real ComfyUI backend."

    workflow_path = _workflow_path(COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH)
    if not workflow_path.is_file():
        return False, f"Text -> Video workflow missing: {workflow_path}"

    try:
        with httpx.Client(
            base_url=COMFYUI_BASE_URL.rstrip("/"),
            timeout=_COMFY_TIMEOUT_SECONDS,
        ) as client:
            response = client.get("/object_info")
            response.raise_for_status()
            object_info = response.json()
    except Exception as exc:  # noqa: BLE001 - readiness should degrade to unavailable.
        return False, f"ComfyUI unavailable at {COMFYUI_BASE_URL}: {exc}"

    try:
        workflow_text = workflow_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"Text -> Video workflow unreadable: {exc}"
    if "EmptyLTXVLatentVideo" not in workflow_text:
        # Not the LTX workflow (for example Wan 2.1 1.3B on an 8 GB GPU): check the
        # workflow's own nodes and model files instead of the LTX-specific list.
        return _workflow_models_ready(workflow_text, object_info)

    missing_nodes = sorted(
        node for node in _TEXT_TO_VIDEO_REQUIRED_NODES if node not in object_info
    )
    if missing_nodes:
        return False, "Missing ComfyUI nodes: " + ", ".join(missing_nodes)

    checkpoint_options = _loader_options(
        object_info, "CheckpointLoaderSimple", "ckpt_name"
    )
    ltx_loader_options = _loader_options(
        object_info, "LTXAVTextEncoderLoader", "ckpt_name"
    )
    text_encoder_options = _loader_options(
        object_info, "LTXAVTextEncoderLoader", "text_encoder"
    )
    lora_options = _loader_options(object_info, "LoraLoaderModelOnly", "lora_name")
    if (
        COMFYUI_VIDEO_MODEL_NAME not in checkpoint_options
        and COMFYUI_VIDEO_MODEL_NAME not in ltx_loader_options
    ):
        return False, f"LTX model not listed in ComfyUI: {COMFYUI_VIDEO_MODEL_NAME}"
    if _TEXT_ENCODER_MODEL not in text_encoder_options:
        return False, f"LTX text encoder not listed in ComfyUI: {_TEXT_ENCODER_MODEL}"
    if _LTX_DISTILLED_LORA_MODEL not in lora_options:
        return False, f"LTX distilled LoRA not listed in ComfyUI: {_LTX_DISTILLED_LORA_MODEL}"

    return True, None


def _video_to_video_ready() -> tuple[bool, str | None]:
    if VIDEO_BACKEND == "mock":
        return True, None
    if VIDEO_BACKEND != "comfyui":
        return False, f"Video backend {VIDEO_BACKEND} is not a real ComfyUI backend."
    workflow_path = _workflow_path(COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH)
    if not workflow_path.is_file():
        return False, f"Video -> Video workflow missing: {workflow_path}"

    try:
        with httpx.Client(
            base_url=COMFYUI_BASE_URL.rstrip("/"),
            timeout=_COMFY_TIMEOUT_SECONDS,
        ) as client:
            response = client.get("/object_info")
            response.raise_for_status()
            object_info = response.json()
    except Exception as exc:  # noqa: BLE001 - readiness should degrade to unavailable.
        return False, f"ComfyUI unavailable at {COMFYUI_BASE_URL}: {exc}"

    missing_nodes = sorted(
        node for node in _VIDEO_TO_VIDEO_REQUIRED_NODES if node not in object_info
    )
    if missing_nodes:
        return False, "Missing ComfyUI nodes: " + ", ".join(missing_nodes)

    checkpoint_options = _loader_options(
        object_info, "CheckpointLoaderSimple", "ckpt_name"
    )
    ltx_loader_options = _loader_options(
        object_info, "LTXAVTextEncoderLoader", "ckpt_name"
    )
    text_encoder_options = _loader_options(
        object_info, "LTXAVTextEncoderLoader", "text_encoder"
    )
    if (
        COMFYUI_VIDEO_MODEL_NAME not in checkpoint_options
        and COMFYUI_VIDEO_MODEL_NAME not in ltx_loader_options
    ):
        return False, f"LTX model not listed in ComfyUI: {COMFYUI_VIDEO_MODEL_NAME}"
    if _TEXT_ENCODER_MODEL not in text_encoder_options:
        return False, f"LTX text encoder not listed in ComfyUI: {_TEXT_ENCODER_MODEL}"

    return True, None


def _video_extension_ready() -> tuple[bool, str | None]:
    if VIDEO_BACKEND == "mock":
        return True, None
    if VIDEO_BACKEND != "comfyui":
        return False, f"Video backend {VIDEO_BACKEND} is not a real ComfyUI backend."
    workflow_path = _workflow_path(COMFYUI_VIDEO_EXTENSION_WORKFLOW_PATH)
    if not workflow_path.is_file():
        return False, f"Video Extension workflow missing: {workflow_path}"
    missing_tools = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing_tools:
        return False, "Video Extension assembly requires: " + ", ".join(missing_tools)

    try:
        with httpx.Client(
            base_url=COMFYUI_BASE_URL.rstrip("/"),
            timeout=_COMFY_TIMEOUT_SECONDS,
        ) as client:
            response = client.get("/object_info")
            response.raise_for_status()
            object_info = response.json()
    except Exception as exc:  # noqa: BLE001 - readiness should degrade to unavailable.
        return False, f"ComfyUI unavailable at {COMFYUI_BASE_URL}: {exc}"

    missing_nodes = sorted(
        node for node in _VIDEO_EXTENSION_REQUIRED_NODES if node not in object_info
    )
    if missing_nodes:
        return False, "Missing ComfyUI nodes: " + ", ".join(missing_nodes)

    checkpoint_options = _loader_options(
        object_info, "CheckpointLoaderSimple", "ckpt_name"
    )
    ltx_loader_options = _loader_options(
        object_info, "LTXAVTextEncoderLoader", "ckpt_name"
    )
    text_encoder_options = _loader_options(
        object_info, "LTXAVTextEncoderLoader", "text_encoder"
    )
    if (
        COMFYUI_VIDEO_MODEL_NAME not in checkpoint_options
        and COMFYUI_VIDEO_MODEL_NAME not in ltx_loader_options
    ):
        return False, f"LTX model not listed in ComfyUI: {COMFYUI_VIDEO_MODEL_NAME}"
    if _TEXT_ENCODER_MODEL not in text_encoder_options:
        return False, f"LTX text encoder not listed in ComfyUI: {_TEXT_ENCODER_MODEL}"

    return True, None


def _video_upscale_ready() -> tuple[bool, str | None]:
    if VIDEO_BACKEND == "mock":
        return True, None
    if VIDEO_BACKEND != "comfyui":
        return False, f"Video backend {VIDEO_BACKEND} is not a real ComfyUI backend."

    workflow_path = _workflow_path(COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH)
    if not workflow_path.is_file():
        return False, f"Video Upscale workflow missing: {workflow_path}"

    try:
        with httpx.Client(
            base_url=COMFYUI_BASE_URL.rstrip("/"),
            timeout=_COMFY_TIMEOUT_SECONDS,
        ) as client:
            response = client.get("/object_info")
            response.raise_for_status()
            object_info = response.json()
    except Exception as exc:  # noqa: BLE001 - readiness should degrade to unavailable.
        return False, f"ComfyUI unavailable at {COMFYUI_BASE_URL}: {exc}"

    missing_nodes = sorted(
        node for node in _VIDEO_UPSCALE_REQUIRED_NODES if node not in object_info
    )
    if missing_nodes:
        return False, "Missing ComfyUI nodes: " + ", ".join(missing_nodes)

    checkpoint_options = _loader_options(
        object_info, "CheckpointLoaderSimple", "ckpt_name"
    )
    upscale_options = _loader_options(
        object_info, "LatentUpscaleModelLoader", "model_name"
    )
    if COMFYUI_VIDEO_MODEL_NAME not in checkpoint_options:
        return False, f"LTX model not listed in ComfyUI: {COMFYUI_VIDEO_MODEL_NAME}"
    if COMFYUI_VIDEO_UPSCALE_MODEL_NAME not in upscale_options:
        return (
            False,
            f"LTX spatial upscaler not listed in ComfyUI: {COMFYUI_VIDEO_UPSCALE_MODEL_NAME}",
        )

    return True, None


@router.get("", response_model=list[VideoOut])
def list_videos(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(VideoGeneration).where(
        VideoGeneration.user_id == user.id, VideoGeneration.deleted_at.is_(None)
    )
    if project_id:
        stmt = stmt.where(VideoGeneration.project_id == project_id)
    stmt = stmt.order_by(VideoGeneration.created_at.desc())
    return db.scalars(stmt).all()


@router.delete("/{video_id}", status_code=204)
def trash_video(video_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Move a generated clip to the recoverable trash (restorable by the admin)."""
    video = db.get(VideoGeneration, video_id)
    if video is None or video.deleted_at is not None or video.user_id != user.id:
        raise HTTPException(status_code=404, detail="Video not found")
    trash.move_to_trash(db, "video", video_id)


@router.get("/{video_id}", response_model=VideoOut)
def get_video(
    video_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    video = db.get(VideoGeneration, video_id)
    if video is None or video.user_id != user.id:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.post("/{video_id}/cancel", response_model=VideoOut)
def cancel_video(video_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    video = db.get(VideoGeneration, video_id)
    if video is None or video.user_id != user.id:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.status in {"queued", "running"}:
        video.status = "cancelled"
        video.error = "Cancelled by user"
        video.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(video)
    return video


@router.post("", response_model=VideoOut, status_code=201)
def create_video(
    payload: VideoCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    provider = payload.provider or (
        "local_h3" if payload.mode in {"text_to_video", "image_to_video", "video_to_video"}
        else "local_ltx"
    )
    if provider == "seedance_api":
        ready, reason = _seedance_ready()
        if not ready:
            raise HTTPException(status_code=409, detail=reason)
        if payload.mode not in {"text_to_video", "image_to_video"}:
            raise HTTPException(
                status_code=409,
                detail="Seedance is only wired for Text -> Video and Image -> Video in Phase 14A.",
            )
    if provider == "local_h3":
        if payload.mode not in {"text_to_video", "image_to_video", "video_to_video"}:
            raise HTTPException(
                status_code=409,
                detail="MiniMax H3 is wired for Text -> Video, Image -> Video and Video -> Video.",
            )
        ready, reason = _h3_controlnet_ready() if payload.mode == "video_to_video" else _h3_ready()
        if not ready:
            raise HTTPException(status_code=409, detail=f"MiniMax H3 is not ready: {reason}")
    if provider == "local_wan":
        if payload.mode != "image_to_video":
            raise HTTPException(
                status_code=409,
                detail="Wan 2.1 is only wired for Image -> Video. Use LTX for other modes.",
            )
        ready, reason = _wan_ready()
        if not ready:
            raise HTTPException(
                status_code=409,
                detail=f"Wan 2.1 Image -> Video is not ready: {reason}",
            )

    if provider == "local_ltx" and VIDEO_BACKEND == "comfyui" and payload.mode not in {
        "image_to_video",
        "text_to_video",
        "video_to_video",
        "video_extension",
        "video_upscale",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "This ComfyUI video mode is not wired yet. Use Image -> Video "
                "or switch the video backend to mock."
            ),
        )
    if provider == "local_ltx" and VIDEO_BACKEND == "comfyui" and payload.mode == "text_to_video":
        ready, reason = _text_to_video_ready()
        if not ready:
            raise HTTPException(
                status_code=409,
                detail=f"Text -> Video is not ready: {reason}",
            )
    if provider == "local_ltx" and VIDEO_BACKEND == "comfyui" and payload.mode == "video_upscale":
        ready, reason = _video_upscale_ready()
        if not ready:
            raise HTTPException(
                status_code=409,
                detail=f"Video Upscale is not ready: {reason}",
            )
    if provider == "local_ltx" and VIDEO_BACKEND == "comfyui" and payload.mode == "video_to_video":
        ready, reason = _video_to_video_ready()
        if not ready:
            raise HTTPException(
                status_code=409,
                detail=f"Video -> Video is not ready: {reason}",
            )
    if provider == "local_ltx" and VIDEO_BACKEND == "comfyui" and payload.mode == "video_extension":
        ready, reason = _video_extension_ready()
        if not ready:
            raise HTTPException(
                status_code=409,
                detail=f"Video Extension is not ready: {reason}",
            )

    project = db.get(Project, payload.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    # Source image comes from a completed product scene, or an explicit URL.
    source_image_url = payload.source_image_url or ""
    if payload.product_scene_id is not None:
        scene = db.get(ProductSceneGeneration, payload.product_scene_id)
        if scene is None or scene.user_id != user.id or scene.project_id != project.id:
            raise HTTPException(status_code=404, detail="Product scene not found")
        if scene.status != "completed" or not scene.result_url:
            raise HTTPException(
                status_code=409, detail="Product scene is not completed yet"
            )
        source_image_url = scene.result_url

    # text_to_video needs no source; every other mode requires one.
    if payload.mode != "text_to_video" and not source_image_url:
        raise HTTPException(
            status_code=400,
            detail="Provide product_scene_id or source_image_url for this mode",
        )

    # Second line of defense: reject unsafe/incompatible source URLs before any job
    # is created or credits reserved. image_to_video takes an image; video modes
    # take a video. (A trusted product-scene result_url still passes these checks.)
    if payload.mode != "text_to_video":
        # Backend is the security boundary: reject Windows paths, traversal,
        # external URLs and non-/storage sources. Precise per-mode file type
        # (image vs video) is enforced by the frontend (first line of defense);
        # local mock/derived outputs use varied extensions (.svg/.html), so the
        # backend does not hard-fail on extension here.
        source_image_url = validate_source_media_url(source_image_url, allowed_exts=None)

    brief = None
    if payload.brief_id is not None:
        brief = load_project_brief(db, project.id, payload.brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="Creative brief not found")

    # Reject before expensive generation if the active family user cannot afford
    # this video plus any in-flight video jobs already reserved. Mirrors the
    # image generation reservation check; the actual charge happens on success.
    active_cost = db.scalar(
        select(func.coalesce(func.sum(VideoGeneration.credits_cost), 0)).where(
            VideoGeneration.user_id == user.id,
            VideoGeneration.status.in_(("queued", "running")),
        )
    )
    reserved_credits = int(active_cost or 0)
    cost = _provider_cost(provider)
    if user.credits - reserved_credits < cost:
        raise HTTPException(
            status_code=402,
            detail=f"Not enough credits for a video generation (cost: {cost}).",
        )

    video = VideoGeneration(
        user_id=user.id,
        project_id=project.id,
        product_scene_id=payload.product_scene_id,
        source_image_url=source_image_url,
        mode=payload.mode,
        provider=provider,
        prompt=with_brief_context(payload.prompt, brief),
        motion_preset=payload.motion_preset,
        duration_seconds=payload.duration_seconds,
        quality_preset=payload.quality_preset,
        credits_cost=cost,
        status="queued",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    enqueue_video(video.id)
    return video
