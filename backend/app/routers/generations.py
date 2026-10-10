import json
import shutil
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..services.transcription import resolve_storage_url
from ..config import (
    BASE_DIR,
    COMFYUI_BASE_URL,
    COMFYUI_IMAGE_EDIT_WORKFLOW_PATH,
    CREDITS_PER_GENERATION,
    CREDITS_PER_OPENAI_IMAGE,
    CREDITS_PER_OPENAI_IMAGE_EDIT,
    GENERATOR_BACKEND,
    IMAGE_QUALITY_PRESET,
    STORAGE_DIR,
)
from ..database import get_db
from ..deps import get_current_user
from ..models import Generation, Project, User
from ..schemas import (
    FaceRefineStatusOut,
    GenerationCreate,
    GenerationOut,
    ImageModeOption,
    ImageModeOut,
    ImagePresetOut,
    ImagePresetsOut,
    ImageProviderReadiness,
    StylePresetOut,
)
from ..services import face_check, face_refine, image_modes, image_presets, prompt_presets
from ..services.generation_jobs import enqueue_generation
from ..services.integrations import get_private_provider_config

router = APIRouter(prefix="/api/generations", tags=["generations"])
_ALLOWED_SOURCE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _combo_options(info: dict, node: str, field: str) -> list[str]:
    try:
        spec = info[node]["input"]["required"][field]
        values = spec[0] if isinstance(spec, list) and spec else []
        return [str(x) for x in values] if isinstance(values, list) else []
    except Exception:  # noqa: BLE001 - readiness probes are best effort.
        return []


def _workflow_path(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else BASE_DIR / p


def _local_image_edit_ready() -> tuple[bool, str | None]:
    workflow = _workflow_path(COMFYUI_IMAGE_EDIT_WORKFLOW_PATH)
    if not workflow.is_file():
        return False, f"Local Qwen Image Edit workflow is missing: {COMFYUI_IMAGE_EDIT_WORKFLOW_PATH}."
    if GENERATOR_BACKEND != "comfyui":
        return False, "Local Image Edit requires GENERATOR_BACKEND=comfyui."
    try:
        resp = httpx.get(f"{COMFYUI_BASE_URL.rstrip('/')}/object_info", timeout=5.0)
        resp.raise_for_status()
        info = resp.json()
    except Exception:  # noqa: BLE001
        return False, f"ComfyUI is offline at {COMFYUI_BASE_URL}."

    required_nodes = [
        "LoadImage",
        "UNETLoader",
        "CLIPLoader",
        "VAELoader",
        "TextEncodeQwenImageEdit",
        "VAEEncode",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ]
    missing_nodes = [node for node in required_nodes if node not in info]
    if missing_nodes:
        return False, "Missing ComfyUI nodes: " + ", ".join(missing_nodes) + "."

    checks = [
        ("UNETLoader", "unet_name", "qwen_image_edit_2509_fp8_e4m3fn.safetensors"),
        ("CLIPLoader", "clip_name", "qwen_2.5_vl_7b_fp8_scaled.safetensors"),
        ("VAELoader", "vae_name", "qwen_image_vae.safetensors"),
    ]
    missing_models = [
        filename
        for node, field, filename in checks
        if filename not in _combo_options(info, node, field)
    ]
    if missing_models:
        return False, "Missing ComfyUI models: " + ", ".join(missing_models) + "."
    return True, None


def _openai_ready() -> tuple[bool, str | None]:
    cfg = get_private_provider_config("openai")
    if not cfg.get("enabled") or not cfg.get("api_key"):
        return False, "OpenAI provider is not configured. Admin setup required."
    if not cfg.get("base_url"):
        return False, "OpenAI provider base URL is missing. Admin setup required."
    return True, None


def _provider_cost(provider: str, mode: str) -> int:
    if provider == "openai_image_api":
        return (
            CREDITS_PER_OPENAI_IMAGE_EDIT
            if mode == "image_edit"
            else CREDITS_PER_OPENAI_IMAGE
        )
    return CREDITS_PER_GENERATION


@router.post("/source-upload", status_code=201)
def upload_generation_source(
    project_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload a standalone source/reference image for Image Edit.

    This deliberately does not create a ProductAsset, so product uploads keep
    their project-required semantics. If a project_id is supplied, validate it
    for ownership; the eventual generation carries the project association.
    """
    if project_id:
        project = db.get(Project, project_id)
        if project is None or project.user_id != user.id:
            raise HTTPException(status_code=404, detail="Project not found")

    original_name = Path(file.filename or "source").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_SOURCE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Source upload must be an image file")

    source_dir = STORAGE_DIR / "image-edit-sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    destination = source_dir / stored_name
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    return {
        "source_image_url": f"/storage/image-edit-sources/{stored_name}",
        "filename": stored_name,
        "project_id": project_id,
    }


@router.post("/reference-upload", status_code=201)
def upload_reference_image(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    """Upload a reference picture (clothes, a room, an object) for a look.

    A picture with a face is refused: the editor copies the face into the avatar. If the local
    vision model can't be reached the picture is accepted and `checked` is false.
    """
    original_name = Path(file.filename or "reference").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in _ALLOWED_SOURCE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Reference upload must be an image file")
    source_dir = STORAGE_DIR / "image-edit-sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    destination = source_dir / stored_name
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    has_face = face_check.image_has_face(destination)
    if has_face:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail="That picture shows a face, and it would replace your avatar's face. Use a picture of clothes, a room or an object.",
        )
    return {"source_image_url": f"/storage/image-edit-sources/{stored_name}", "filename": stored_name, "checked": has_face is False}


@router.get("/modes", response_model=list[ImageModeOption])
def list_generation_modes():
    openai_ready, openai_note = _openai_ready()
    local_edit_ready, local_edit_note = _local_image_edit_ready()
    modes = [
        (
            "text_to_image",
            "Text -> Image",
            "Create artwork from a text prompt.",
            False,
        ),
        (
            "image_edit",
            "Image Edit",
            "Use a source image as edit/reference input.",
            True,
        ),
    ]
    return [
        ImageModeOption(
            id=mode_id,
            name=name,
            description=description,
            source_required=source_required,
            providers={
                "local_comfyui": ImageProviderReadiness(
                    available=mode_id == "text_to_image" or local_edit_ready,
                    cost=CREDITS_PER_GENERATION,
                    note=(
                        None
                        if mode_id == "text_to_image" or local_edit_ready
                        else local_edit_note
                    ),
                ),
                "openai_image_api": ImageProviderReadiness(
                    available=openai_ready,
                    cost=_provider_cost("openai_image_api", mode_id),
                    note=openai_note if not openai_ready else None,
                ),
            },
        )
        for mode_id, name, description, source_required in modes
    ]


@router.get("/presets", response_model=ImagePresetsOut)
def list_image_presets():
    """Image Quality Modes + underlying model presets + style presets + refine status."""
    return ImagePresetsOut(
        quality_presets=[ImagePresetOut(**p) for p in image_presets.list_image_presets()],
        style_presets=[StylePresetOut(**s) for s in prompt_presets.list_style_presets()],
        image_modes=[ImageModeOut(**m) for m in image_modes.list_image_modes()],
        face_refine=FaceRefineStatusOut(**face_refine.refine_readiness()),
    )


@router.get("", response_model=list[GenerationOut])
def list_generations(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    stmt = (
        select(Generation)
        .where(Generation.user_id == user.id, Generation.deleted_at.is_(None))
        .order_by(Generation.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.get("/{generation_id}", response_model=GenerationOut)
def get_generation(
    generation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    gen = db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    return gen


@router.post("/{generation_id}/cancel", response_model=GenerationOut)
def cancel_generation(generation_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    gen = db.get(Generation, generation_id)
    if gen is None or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    if gen.status in {"queued", "running"}:
        gen.status = "cancelled"
        gen.error = "Cancelled by user"
        db.commit()
        db.refresh(gen)
    return gen


@router.post("", response_model=GenerationOut, status_code=201)
def create_generation(
    payload: GenerationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    provider = payload.provider or "local_comfyui"
    mode = payload.mode or "text_to_image"
    if payload.media_type != "image" and provider == "openai_image_api":
        raise HTTPException(
            status_code=409,
            detail="OpenAI Image API is only wired for image/art generation.",
        )
    if provider == "openai_image_api":
        ready, reason = _openai_ready()
        if not ready:
            raise HTTPException(status_code=409, detail=reason)
        if mode not in {"text_to_image", "image_edit"}:
            raise HTTPException(status_code=409, detail="OpenAI image mode is not supported.")
        if mode == "image_edit" and not payload.source_image_url:
            raise HTTPException(
                status_code=400,
                detail="OpenAI image edit requires source_image_url.",
            )
    elif mode == "image_edit" and False:
        raise HTTPException(
            status_code=409,
            detail=(
                "Image Edit currently runs through the OpenAI Image API provider — enable it in "
                "Admin → Integrations and select it as the provider. A local edit route is not wired yet."
            ),
        )

    if provider == "local_comfyui" and mode == "image_edit":
        if not payload.source_image_url:
            raise HTTPException(
                status_code=400,
                detail="Local Image Edit requires source_image_url.",
            )
        ready, reason = _local_image_edit_ready()
        if not ready:
            raise HTTPException(status_code=409, detail=reason)

    # Local image quality: an Image Quality Mode (preferred) selects both the model
    # and the prompt enhancer and always resolves to a ready model (safe local
    # default preserved). A raw quality_preset is still honored for direct control.
    quality_preset: str | None = None
    use_mode = False
    if provider == "local_comfyui" and mode != "image_edit":
        if payload.image_mode:
            if not image_modes.is_known_mode(payload.image_mode):
                raise HTTPException(status_code=400, detail="Unknown image quality mode.")
            quality_preset = image_modes.effective_preset(payload.image_mode)
            use_mode = True
        else:
            quality_preset = payload.quality_preset or IMAGE_QUALITY_PRESET
            if not image_presets.is_known_preset(quality_preset):
                raise HTTPException(status_code=400, detail="Unknown image quality preset.")
            # Only gate on the real backend; the mock backend ignores the preset.
            # Never fake output when a higher-quality model isn't installed.
            if GENERATOR_BACKEND == "comfyui" and not image_presets.preset_ready(quality_preset):
                raise HTTPException(
                    status_code=409,
                    detail=f"Image model setup required for '{quality_preset}'. Install the model in ComfyUI or pick a ready preset.",
                )

    cost = _provider_cost(provider, mode)
    active_count = db.scalar(
        select(func.count())
        .select_from(Generation)
        .where(
            Generation.user_id == user.id,
            Generation.status.in_(("queued", "running")),
        )
    )
    active_cost = db.scalar(
        select(func.coalesce(func.sum(Generation.credits_cost), 0)).where(
            Generation.user_id == user.id,
            Generation.status.in_(("queued", "running")),
        )
    )
    reserved_credits = int(active_cost or 0) or (active_count or 0) * CREDITS_PER_GENERATION
    if user.credits - reserved_credits < cost:
        raise HTTPException(status_code=402, detail="Not enough credits")

    if payload.project_id is not None:
        project = db.get(Project, payload.project_id)
        if project is None or project.user_id != user.id:
            raise HTTPException(status_code=404, detail="Project not found")

    if use_mode:
        final_prompt = image_modes.apply_mode_prompt(payload.prompt, payload.image_mode)
    else:
        final_prompt = prompt_presets.apply_style_preset(payload.prompt, payload.style_preset)

    if payload.reference_image_urls:
        if provider == "openai_image_api" or mode != "image_edit":
            raise HTTPException(status_code=400, detail="Reference images work with local Image Edit only.")
        for ref in payload.reference_image_urls:
            if Path(ref).suffix.lower() not in _ALLOWED_SOURCE_EXTENSIONS:
                raise HTTPException(status_code=400, detail="Reference images must be image files.")
            try:
                resolve_storage_url(ref)  # path-traversal-safe
            except RuntimeError as exc:
                raise HTTPException(status_code=400, detail="A reference image was not found. Upload it again.") from exc

    gen = Generation(
        user_id=user.id,
        project_id=payload.project_id,
        prompt=final_prompt,
        media_type=payload.media_type,
        provider=provider,
        provider_model=(
            get_private_provider_config("openai").get("image_model")
            if provider == "openai_image_api"
            else (
                "qwen_image_edit_2509_fp8_e4m3fn.safetensors"
                if mode == "image_edit"
                else quality_preset
            )
        ),
        source_image_url=payload.source_image_url if mode == "image_edit" else None,
        reference_image_urls=json.dumps(payload.reference_image_urls) if payload.reference_image_urls and mode == "image_edit" else None,
        credits_cost=cost if provider == "openai_image_api" else 0,
        status="queued",
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)
    enqueue_generation(gen.id)
    return gen
