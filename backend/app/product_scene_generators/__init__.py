"""Product-scene generator factory.

Anything other than "comfyui" falls back to the mock generator, so a missing or
misconfigured backend never takes the app down. Within the comfyui backend the
mode (per-request, or the configured default) selects the workflow:

  * ipadapter -> IPAdapter workflow (stronger preservation, custom nodes)
  * inpaint   -> inpaint workflow (mask-based preservation; falls back to the
                 configured mode when no mask is available)
  * anything else -> img2img workflow
"""
from .. import config
from ..config import (
    COMFYUI_BASE_URL,
    COMFYUI_PRODUCT_SCENE_ADVERTISING_SCENE_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_CREATIVE_FASHION_EDIT_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_FASHION_EDITORIAL_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_FLUX_KONTEXT_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_HIDREAM_E1_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_INPAINT_FALLBACK,
    COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_AUTOSEG_FACEPROTECT_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_AUTOSEG_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_HUMANPARSE_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_CLOTHING_STYLE_EDIT_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_INPAINT_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_MASKED_ATTRIBUTE_EDIT_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_IPADAPTER_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_MODE,
    COMFYUI_PRODUCT_SCENE_POSE_EDIT_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_POSE_IDENTITY_PRESET_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_POSE_IDENTITY_REFERENCE_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_POSE_PRESET_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_POSE_REFERENCE_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_QWEN_IMAGE_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_POLISHED_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_WORKFLOW_PATH,
    COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH,
    PRODUCT_SCENE_BACKEND,
    PRODUCT_SCENE_MODEL,
)
from .base import ProductSceneGenerator, ProductSceneResult
from .comfyui import (
    ADVERTISING_SCENE_MODE,
    ATTRIBUTE_EDIT_MODE,
    PARSE_MANUAL,
    resolve_parse_class,
    resolve_seg,
    CHARACTER_REIMAGINATION_MODE,
    CINEMATIC_SCENE_BUILDER_MODE,
    CLOTHING_STYLE_EDIT_MODE,
    CREATIVE_FASHION_EDIT_MODE,
    CREATIVE_EDIT_MODE,
    FASHION_TRANSFORMATION_MODE,
    FASHION_EDITORIAL_MODE,
    FILM_SCENE_MODE,
    INPAINT_MODE,
    IPADAPTER_MODE,
    POSE_EDIT_MODE,
    POSE_STYLIZED_MODE,
    SEGMENTED_COMPOSITE_MODE,
    SEGMENTED_COMPOSITE_POLISHED_MODE,
    ComfyUIProductSceneGenerator,
)
from .mock import MockProductSceneGenerator

__all__ = [
    "ComfyUIProductSceneGenerator",
    "MockProductSceneGenerator",
    "ProductSceneGenerator",
    "ProductSceneResult",
    "get_product_scene_generator",
]

_MODEL_WORKFLOWS = {
    "flux-kontext": COMFYUI_PRODUCT_SCENE_FLUX_KONTEXT_WORKFLOW_PATH,
    "qwen-image": COMFYUI_PRODUCT_SCENE_QWEN_IMAGE_WORKFLOW_PATH,
    "hidream-e1": COMFYUI_PRODUCT_SCENE_HIDREAM_E1_WORKFLOW_PATH,
}

# Preserve / Flux-and-RemBG creative modes -> self-contained workflow files
# (Phase C9, C10B). Flux Kontext (creative_fashion_edit) is now a *preserve*
# specialist reachable only by explicit selection — it is NOT in the Transform
# set below, so transformation modes never silently fall back to Flux.
_CREATIVE_MODE_WORKFLOWS = {
    SEGMENTED_COMPOSITE_MODE: COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_WORKFLOW_PATH,
    SEGMENTED_COMPOSITE_POLISHED_MODE: (
        COMFYUI_PRODUCT_SCENE_SEGMENTED_COMPOSITE_POLISHED_WORKFLOW_PATH
    ),
    ADVERTISING_SCENE_MODE: COMFYUI_PRODUCT_SCENE_ADVERTISING_SCENE_WORKFLOW_PATH,
    FASHION_EDITORIAL_MODE: COMFYUI_PRODUCT_SCENE_FASHION_EDITORIAL_WORKFLOW_PATH,
    CREATIVE_FASHION_EDIT_MODE: (
        COMFYUI_PRODUCT_SCENE_CREATIVE_FASHION_EDIT_WORKFLOW_PATH
    ),
}

# Transform Mode (Path 2) -> Qwen Image Edit. These are the transformation-first
# Creative Edit workflows. They route to Qwen with model validation enabled so a
# missing Qwen install fails with a clear error rather than silently rendering
# through Flux.
_TRANSFORM_MODES = {
    CREATIVE_EDIT_MODE,
    CHARACTER_REIMAGINATION_MODE,
    FASHION_TRANSFORMATION_MODE,
    CINEMATIC_SCENE_BUILDER_MODE,
    FILM_SCENE_MODE,
}
# clothing_style_edit is a *targeted* edit, not a free transform: it gets its own
# Qwen Edit Plus workflow tuned to change only the requested garment.


def _model_workflow_path() -> str:
    return _MODEL_WORKFLOWS.get(PRODUCT_SCENE_MODEL, COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH)


def _qwen_creative_workflow() -> tuple[str, str]:
    """(workflow_path, model_key) for the active Qwen precision. Read at call
    time so the Workflow Manager / tests can switch precision at runtime."""
    if getattr(config, "CREATIVE_QWEN_PRECISION", "gguf") == "fp8":
        return config.COMFYUI_PRODUCT_SCENE_CREATIVE_QWEN_EDIT_FP8_WORKFLOW_PATH, "qwen-image"
    return config.COMFYUI_PRODUCT_SCENE_CREATIVE_QWEN_EDIT_WORKFLOW_PATH, "qwen-image-gguf"


def get_product_scene_generator(
    mode: str | None = None, target_attribute: str | None = None
) -> ProductSceneGenerator:
    if PRODUCT_SCENE_BACKEND != "comfyui":
        return MockProductSceneGenerator()

    effective_mode = mode or COMFYUI_PRODUCT_SCENE_MODE
    model_workflow_path = _model_workflow_path()

    if effective_mode == IPADAPTER_MODE:
        return ComfyUIProductSceneGenerator(
            COMFYUI_BASE_URL,
            COMFYUI_PRODUCT_SCENE_IPADAPTER_WORKFLOW_PATH,
            IPADAPTER_MODE,
            model_key=PRODUCT_SCENE_MODEL,
        )

    if effective_mode == INPAINT_MODE:
        if COMFYUI_PRODUCT_SCENE_INPAINT_FALLBACK == IPADAPTER_MODE:
            fallback_mode = IPADAPTER_MODE
            fallback_workflow = COMFYUI_PRODUCT_SCENE_IPADAPTER_WORKFLOW_PATH
        else:
            fallback_mode = "img2img"
            fallback_workflow = model_workflow_path
        return ComfyUIProductSceneGenerator(
            COMFYUI_BASE_URL,
            COMFYUI_PRODUCT_SCENE_INPAINT_WORKFLOW_PATH,
            INPAINT_MODE,
            fallback_mode=fallback_mode,
            fallback_workflow_path=fallback_workflow,
            model_key=PRODUCT_SCENE_MODEL,
        )

    if effective_mode == POSE_EDIT_MODE:
        # Identity Pose (SDXL + OpenPose + IPAdapter -> Qwen refine). A bundled
        # preset skeleton (target_attribute names it) or a DWPose-d reference
        # photo drives the pose; the source image conditions identity via
        # IPAdapter in the SDXL stage.
        is_preset = (target_attribute or "").strip().lower() in config.POSE_PRESETS
        pose_workflow = (
            COMFYUI_PRODUCT_SCENE_POSE_IDENTITY_PRESET_WORKFLOW_PATH
            if is_preset
            else COMFYUI_PRODUCT_SCENE_POSE_IDENTITY_REFERENCE_WORKFLOW_PATH
        )
        return ComfyUIProductSceneGenerator(
            COMFYUI_BASE_URL, pose_workflow, POSE_EDIT_MODE, model_key="pose-ipadapter"
        )

    if effective_mode == POSE_STYLIZED_MODE:
        # Stylized Pose fallback (SDXL + OpenPose -> Qwen refine). A bundled preset skeleton
        # (target_attribute names it) or a DWPose-d reference photo drives the
        # pose. This preserves Claude's approximate-identity path.
        is_preset = (target_attribute or "").strip().lower() in config.POSE_PRESETS
        pose_workflow = (
            COMFYUI_PRODUCT_SCENE_POSE_PRESET_WORKFLOW_PATH
            if is_preset
            else COMFYUI_PRODUCT_SCENE_POSE_REFERENCE_WORKFLOW_PATH
        )
        return ComfyUIProductSceneGenerator(
            COMFYUI_BASE_URL, pose_workflow, POSE_STYLIZED_MODE, model_key=""
        )

    if effective_mode == ATTRIBUTE_EDIT_MODE:
        if target_attribute:
            parse_class = resolve_parse_class(target_attribute)
            if parse_class and parse_class != PARSE_MANUAL:
                # Human-parsing: precise class mask (pants, hair, face, shoes,
                # dress, single upper garment). First choice for these.
                return ComfyUIProductSceneGenerator(
                    COMFYUI_BASE_URL,
                    COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_HUMANPARSE_WORKFLOW_PATH,
                    ATTRIBUTE_EDIT_MODE,
                    model_key="qwen-image-gguf-humanparse",
                )
            if parse_class == PARSE_MANUAL:
                # Ambiguous overlapping garment (shirt vs jacket) -> manual mask.
                return ComfyUIProductSceneGenerator(
                    COMFYUI_BASE_URL,
                    COMFYUI_PRODUCT_SCENE_MASKED_ATTRIBUTE_EDIT_WORKFLOW_PATH,
                    ATTRIBUTE_EDIT_MODE,
                    model_key="qwen-image-gguf-masked",
                )
            # Otherwise GroundingDINO+SAM open-vocab (tie, glasses, logos, ...).
            _, exclude = resolve_seg(target_attribute)
            autoseg_workflow = (
                COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_AUTOSEG_FACEPROTECT_WORKFLOW_PATH
                if exclude
                else COMFYUI_PRODUCT_SCENE_ATTRIBUTE_EDIT_AUTOSEG_WORKFLOW_PATH
            )
            return ComfyUIProductSceneGenerator(
                COMFYUI_BASE_URL,
                autoseg_workflow,
                ATTRIBUTE_EDIT_MODE,
                model_key="qwen-image-gguf-autoseg",
            )
        # No target_attribute -> manual Masked Attribute Editor: regenerate only
        # inside a user-supplied mask and composite the original back outside it.
        return ComfyUIProductSceneGenerator(
            COMFYUI_BASE_URL,
            COMFYUI_PRODUCT_SCENE_MASKED_ATTRIBUTE_EDIT_WORKFLOW_PATH,
            ATTRIBUTE_EDIT_MODE,
            model_key="qwen-image-gguf-masked",
        )

    if effective_mode == CLOTHING_STYLE_EDIT_MODE:
        # Targeted clothing edit -> dedicated Qwen Edit Plus graph (GGUF) with a
        # strong negative prompt to prevent duplication and outfit drift.
        return ComfyUIProductSceneGenerator(
            COMFYUI_BASE_URL,
            COMFYUI_PRODUCT_SCENE_CLOTHING_STYLE_EDIT_WORKFLOW_PATH,
            CLOTHING_STYLE_EDIT_MODE,
            model_key="qwen-image-gguf",
        )

    if effective_mode in _TRANSFORM_MODES:
        # Transform Mode -> Qwen Image Edit. model_key drives node/weight
        # validation so a missing Qwen install raises a clear error instead of
        # silently falling back to Flux (per the Film Studio routing policy).
        qwen_workflow, qwen_model_key = _qwen_creative_workflow()
        return ComfyUIProductSceneGenerator(
            COMFYUI_BASE_URL,
            qwen_workflow,
            effective_mode,
            model_key=qwen_model_key,
        )

    if effective_mode in _CREATIVE_MODE_WORKFLOWS:
        # Preserve / Flux-and-RemBG modes are self-contained workflows, so
        # model_key is left empty to skip the per-image-model node validation.
        return ComfyUIProductSceneGenerator(
            COMFYUI_BASE_URL,
            _CREATIVE_MODE_WORKFLOWS[effective_mode],
            effective_mode,
            model_key="",
        )

    return ComfyUIProductSceneGenerator(
        COMFYUI_BASE_URL, model_workflow_path, "img2img", model_key=PRODUCT_SCENE_MODEL
    )
