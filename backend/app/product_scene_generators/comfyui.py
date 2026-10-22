"""Real ComfyUI product-scene adapter.

Supports three modes, in increasing order of product-identity preservation:

  * img2img   - product encoded as the init latent, scene re-rendered around it.
  * ipadapter - product image conditions an IPAdapter node (custom nodes needed).
  * inpaint   - product + mask: the masked product region is kept and only the
                background is regenerated (strongest preservation). Needs a mask.

Mode and workflow are chosen by the factory and baked into the instance. When
inpaint mode is requested but no mask is supplied, the adapter falls back to a
configured mode (img2img or ipadapter) so the job still succeeds.

Common flow per run: resolve image(s) -> upload to ComfyUI (/upload/image) ->
inject into the workflow -> POST /prompt -> poll /history -> download /view ->
save under STORAGE_DIR/product-scenes/<id>.png. Returns the same
ProductSceneResult shape as the mock generator.

Mirrors (rather than shares) the text-to-image adapter's request pattern so the
locked text-to-image adapter stays untouched.
"""
import asyncio
import json
import logging
import mimetypes
import random
from pathlib import Path

import httpx

from ..config import (
    BASE_DIR,
    COMFYUI_BASE_URL,
    COMFYUI_PRODUCT_SCENE_MODE,
    COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH,
    STORAGE_DIR,
)
from .base import ProductSceneGenerator, ProductSceneResult

PROMPT_PLACEHOLDER = "__PROMPT__"
PRESET_PLACEHOLDER = "__PRESET__"
PRODUCT_IMAGE_PLACEHOLDER = "__PRODUCT_IMAGE__"
PRODUCT_MASK_PLACEHOLDER = "__PRODUCT_MASK__"
SEG_PROMPT_PLACEHOLDER = "__SEG_PROMPT__"
EXCLUDE_PROMPT_PLACEHOLDER = "__EXCLUDE_PROMPT__"
PARSE_CLASS_PLACEHOLDER = "__PARSE_CLASS__"
POSE_SKELETON_PLACEHOLDER = "__POSE_SKELETON__"

# Sentinel: garments that overlap a held/worn jacket and cannot be auto-separated
# reliably -> require a manual mask.
PARSE_MANUAL = "MANUAL"

# attribute -> SCHP/LIP parse class for the human-parsing route. PARSE_MANUAL
# forces a manual mask (shirt vs jacket ambiguity). Unmapped -> GroundingDINO.
_PARSE_ATTR = {
    "pants": "Pants",
    "trousers": "Pants",
    "shoes": "Shoes",
    "shoe": "Shoes",
    "footwear": "Shoes",
    "face": "Face",
    "makeup": "Face",
    "hair": "Hair",
    "hairstyle": "Hair",
    "haircut": "Hair",
    "dress": "Dress",
    "skirt": "Skirt",
    "hat": "Hat",
    "jacket": "upper_garment",
    "coat": "upper_garment",
    "blazer": "upper_garment",
    "outerwear": "upper_garment",
    "upper garment": "upper_garment",
    "upper-clothes": "upper_garment",
    # Ambiguous with a held/worn jacket -> manual mask required.
    "shirt": PARSE_MANUAL,
    "dress shirt": PARSE_MANUAL,
    "button-down": PARSE_MANUAL,
    "button-down shirt": PARSE_MANUAL,
    "button down shirt": PARSE_MANUAL,
}

AMBIGUOUS_GARMENT_WARNING = (
    "Shirt vs jacket cannot be separated automatically when a jacket overlaps the "
    "shirt — supply a manual mask of the shirt region."
)


def resolve_parse_class(attribute: str | None) -> str | None:
    """attribute -> LIP parse class, PARSE_MANUAL (ambiguous), or None (no
    human-parse route; fall through to GroundingDINO open-vocab)."""
    if not attribute or not attribute.strip():
        return None
    return _PARSE_ATTR.get(attribute.strip().lower())

# attribute -> (GroundingDINO segmentation prompt, exclusion prompt or None).
# Tightens auto-seg specificity so e.g. "shirt" does not also grab the jacket.
_ATTRIBUTE_SEG = {
    "shirt": ("shirt, not jacket, not coat", "jacket, coat, outerwear"),
    "jacket": ("jacket, coat, outerwear", None),
    "coat": ("jacket, coat, outerwear", None),
    "pants": ("pants, trousers, legs", None),
    "trousers": ("pants, trousers, legs", None),
    "hair": ("hair, not face, not forehead", "face"),
    "hairstyle": ("hair, not face, not forehead", "face"),
    "haircut": ("hair, not face, not forehead", "face"),
    "beard": ("beard, facial hair", "eyes, nose, mouth, forehead"),
    "tie": ("tie, necktie", None),
    "shoes": ("shoes, footwear", None),
    "glasses": ("glasses, eyewear", None),
}


def resolve_seg(attribute: str | None) -> tuple[str | None, str | None]:
    """Map a raw target attribute to (segmentation prompt, exclusion prompt).

    Unknown attributes fall back to the raw text with no exclusion, so arbitrary
    targets still work. Glasses intentionally has no exclusion — its SAM mask is
    already tight, and subtracting the eyes would erase the glasses themselves.
    """
    if not attribute or not attribute.strip():
        return None, None
    return _ATTRIBUTE_SEG.get(attribute.strip().lower(), (attribute.strip(), None))

IMG2IMG_MODE = "img2img"
IPADAPTER_MODE = "ipadapter"
INPAINT_MODE = "inpaint"
SEGMENTED_COMPOSITE_MODE = "segmented_composite"
SEGMENTED_COMPOSITE_POLISHED_MODE = "segmented_composite_polished"
ADVERTISING_SCENE_MODE = "advertising_scene"
FASHION_EDITORIAL_MODE = "fashion_editorial"
CREATIVE_FASHION_EDIT_MODE = "creative_fashion_edit"
CREATIVE_EDIT_MODE = "creative_edit"
CHARACTER_REIMAGINATION_MODE = "character_reimagination"
FASHION_TRANSFORMATION_MODE = "fashion_transformation"
CINEMATIC_SCENE_BUILDER_MODE = "cinematic_scene_builder"
CLOTHING_STYLE_EDIT_MODE = "clothing_style_edit"
POSE_EDIT_MODE = "pose_edit"
POSE_STYLIZED_MODE = "pose_stylized"
FILM_SCENE_MODE = "film_scene"
ATTRIBUTE_EDIT_MODE = "attribute_edit"

# Surfaced to logs (and the UI, once attribute_edit is exposed there). Hair sits
# directly above the forehead, so a loose mask bleeds onto the face.
ATTRIBUTE_EDIT_MASK_WARNING = (
    "Hair edits require a precise mask. Rough masks may alter the face."
)

_IPADAPTER_NODE_PREFIX = "IPAdapter"
# Core ComfyUI nodes the inpaint workflow depends on; verified before submitting.
_INPAINT_REQUIRED_NODES = ("VAEEncodeForInpaint", "LoadImageMask", "InvertMask")
# RemBG nodes the segmented-composite workflow depends on.
_SEGMENTED_REQUIRED_NODES = ("RemBGSession+", "ImageRemoveBackground+")
# The polished composite adds edge-refinement + color-matching nodes.
_SEGMENTED_POLISHED_REQUIRED_NODES = (
    "RemBGSession+",
    "ImageRemoveBackground+",
    "MaskSmooth+",
    "ImageColorMatch+",
    "ImageCompositeMasked",
)

_STORAGE_URL_PREFIX = "/storage/"
_POLL_INTERVAL_SECONDS = 1.5
_POLL_MAX_ATTEMPTS = 200  # ~5 minutes at the interval above
_HTTP_TIMEOUT_SECONDS = 60.0

# Each preset maps to a style descriptor appended to the user's scene prompt.
_PRESET_STYLES = {
    "studio": "professional studio product photography, seamless backdrop, soft diffused lighting",
    "luxury": "luxury product photography, dark moody background, gold accents, dramatic rim lighting",
    "outdoor": "outdoor lifestyle product photo, natural daylight, organic environment",
    "social ad": "vibrant social media advertisement, bright punchy colors, high contrast, eye-catching",
}

# Creative-mode prompt enhancement appended to the user's prompt (Phase C9).
_MODE_STYLES = {
    ADVERTISING_SCENE_MODE: (
        "commercial product photography, premium lighting, clean advertising "
        "composition, high-end campaign visual"
    ),
    FASHION_EDITORIAL_MODE: (
        "editorial fashion photography, luxury magazine style, cinematic "
        "composition, refined environment"
    ),
    CREATIVE_FASHION_EDIT_MODE: (
        "creative fashion edit, true editorial fashion advertising, allow "
        "background/location replacement, moderate pose change, requested "
        "clothing color changes, styling changes, lighting changes, and "
        "stronger composition/framing changes while keeping natural anatomy"
    ),
    CREATIVE_EDIT_MODE: (
        "creative image edit, maintain recognizable identity while allowing new "
        "pose, camera angle, environment, clothing, hairstyle, accessories, "
        "lighting, framing, and composition"
    ),
    CHARACTER_REIMAGINATION_MODE: (
        "character reimagination, preserve core facial identity and recognizability "
        "while allowing age changes, fantasy, cyberpunk, superhero, historical, "
        "or science-fiction transformation"
    ),
    FASHION_TRANSFORMATION_MODE: (
        "fashion transformation, allow full clothing replacement, color changes, "
        "luxury styling, runway/editorial wardrobe, accessories, hair styling, "
        "and fashion campaign direction without preserving original garments"
    ),
    CINEMATIC_SCENE_BUILDER_MODE: (
        "cinematic scene builder, allow dramatic camera angle, wide shot, medium "
        "shot, closeup, tracking-shot feel, cinematic lighting, film still "
        "composition, and story-driven environment"
    ),
    CLOTHING_STYLE_EDIT_MODE: (
        "targeted clothing edit: change only the specified garment's color, "
        "material, or style; keep all other clothing, the face, identity, body "
        "shape, and pose unchanged; single subject only, photorealistic"
    ),
    ATTRIBUTE_EDIT_MODE: (
        "masked attribute edit: change only the content inside the masked region "
        "as instructed; keep everything outside the mask, the face, identity, "
        "body shape, pose, and background unchanged; single subject, photorealistic"
    ),
    POSE_EDIT_MODE: (
        "identity pose edit, use the target OpenPose body position while "
        "preserving the same person, face, hairstyle, clothing, garment colors, "
        "shoes, and product details, then refine and polish"
    ),
    POSE_STYLIZED_MODE: (
        "stylized pose edit, change body position and pose (walking, running, "
        "sitting, runway, action), approximate identity, then restyle and polish"
    ),
    FILM_SCENE_MODE: (
        "cinematic film keyframe, dramatic lighting and camera framing, "
        "production-quality still suitable as the first frame of a film shot"
    ),
    SEGMENTED_COMPOSITE_MODE: (
        "preserve the original subject exactly, replace only the "
        "environment/background, avoid changing clothing, body, pose, or face"
    ),
    SEGMENTED_COMPOSITE_POLISHED_MODE: (
        "preserve the original subject exactly, replace only the "
        "environment/background, avoid changing clothing, body, pose, or face, "
        "natural seamless edges, color-matched lighting, grounded placement"
    ),
}

_LOGGER = logging.getLogger(__name__)
_MODEL_REQUIRED_NODES = {
        "flux-kontext": [
            "LoadImage",
            "FluxKontextImageScale",
            "UNETLoader",
            "DualCLIPLoader",
            "VAELoader",
        "VAEEncode",
        "CLIPTextEncodeFlux",
        "ModelSamplingFlux",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ],
    "qwen-image": [
        "LoadImage",
        "UNETLoader",
        "CLIPLoader",
        "VAELoader",
        ("TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus"),
        "VAEEncode",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ],
    # GGUF Qwen ("Fast") swaps UNETLoader for the ComfyUI-GGUF loader node.
    "qwen-image-gguf": [
        "LoadImage",
        "UnetLoaderGGUF",
        "CLIPLoader",
        "VAELoader",
        ("TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus"),
        "VAEEncode",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ],
    # Masked Attribute Editor: GGUF Qwen edit confined to a mask region, then
    # composited back over the original (so only the masked area changes).
    "qwen-image-gguf-masked": [
        "LoadImage",
        "LoadImageMask",
        "UnetLoaderGGUF",
        "CLIPLoader",
        "VAELoader",
        ("TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus"),
        "VAEEncode",
        "SetLatentNoiseMask",
        "KSampler",
        "VAEDecode",
        "ImageCompositeMasked",
        "SaveImage",
    ],
    # Human-parsing attribute edit: SCHP LIP/ATR produces the class mask.
    "qwen-image-gguf-humanparse": [
        "LoadImage",
        "HumanParseMask",
        "UnetLoaderGGUF",
        "CLIPLoader",
        "VAELoader",
        ("TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus"),
        "VAEEncode",
        "SetLatentNoiseMask",
        "KSampler",
        "VAEDecode",
        "ImageCompositeMasked",
        "SaveImage",
    ],
    # Auto-seg attribute edit: GroundingDINO+SAM build the mask from a text
    # target. MaskComposite is used by the face-protected variant.
    "qwen-image-gguf-autoseg": [
        "LoadImage",
        "GroundingDinoModelLoader (segment anything)",
        "SAMModelLoader (segment anything)",
        "GroundingDinoSAMSegment (segment anything)",
        "UnetLoaderGGUF",
        "CLIPLoader",
        "VAELoader",
        ("TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus"),
        "VAEEncode",
        "SetLatentNoiseMask",
        "KSampler",
        "VAEDecode",
        "ImageCompositeMasked",
        "MaskComposite",
        "SaveImage",
    ],
    "hidream-e1": [
        "LoadImage",
        "UNETLoader",
        "DualCLIPLoader",
        "VAELoader",
        "CLIPTextEncodeHiDream",
        "VAEEncode",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ],
    "pose-ipadapter": [
        "LoadImage",
        "CheckpointLoaderSimple",
        "CLIPVisionLoader",
        "IPAdapterUnifiedLoader",
        "IPAdapterAdvanced",
        "ControlNetLoader",
        "ControlNetApplyAdvanced",
        ("TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus"),
        "UnetLoaderGGUF",
        "CLIPLoader",
        "VAELoader",
        "VAEEncode",
        "KSampler",
        "VAEDecode",
        "SaveImage",
    ],
}

_LOADER_MODEL_INPUTS = {
    "CheckpointLoaderSimple": [("ckpt_name", "CheckpointLoaderSimple")],
    "UNETLoader": [("unet_name", "UNETLoader")],
    "UnetLoaderGGUF": [("unet_name", "UnetLoaderGGUF")],
    "CLIPLoader": [("clip_name", "CLIPLoader")],
    "DualCLIPLoader": [
        ("clip_name1", "DualCLIPLoader"),
        ("clip_name2", "DualCLIPLoader"),
    ],
    "VAELoader": [("vae_name", "VAELoader")],
    "CLIPVisionLoader": [("clip_name", "CLIPVisionLoader")],
    "ControlNetLoader": [("control_net_name", "ControlNetLoader")],
}


def _to_abs(workflow_path: str | None) -> Path | None:
    if workflow_path is None:
        return None
    path = Path(workflow_path)
    return path if path.is_absolute() else BASE_DIR / path


class ComfyUIProductSceneGenerator(ProductSceneGenerator):
    def __init__(
        self,
        base_url: str = COMFYUI_BASE_URL,
        workflow_path: str = COMFYUI_PRODUCT_SCENE_WORKFLOW_PATH,
        mode: str = COMFYUI_PRODUCT_SCENE_MODE,
        fallback_mode: str | None = None,
        fallback_workflow_path: str | None = None,
        model_key: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.mode = mode
        self.workflow_path = _to_abs(workflow_path)
        self.fallback_mode = fallback_mode
        self.fallback_workflow_path = _to_abs(fallback_workflow_path)
        self.model_key = model_key

    # --- helpers -------------------------------------------------------------
    def _resolve_local_path(self, url: str, *, label: str) -> Path:
        if not url.startswith(_STORAGE_URL_PREFIX):
            raise RuntimeError(
                f"Cannot resolve {label} url '{url}' to a local file "
                "(expected a /storage/ path)."
            )
        local = STORAGE_DIR / url[len(_STORAGE_URL_PREFIX) :]
        if not local.is_file():
            raise RuntimeError(f"{label} file not found: {local}")
        return local

    def _effective(self, mask_image_url: str | None) -> tuple[str, Path]:
        """Resolve the mode + workflow actually used for this run, applying the
        no-mask fallback for inpaint mode."""
        if self.mode == INPAINT_MODE and not mask_image_url:
            if not (self.fallback_mode and self.fallback_workflow_path):
                raise RuntimeError(
                    "inpaint mode requires a product mask and no fallback mode "
                    "is configured."
                )
            return self.fallback_mode, self.fallback_workflow_path
        return self.mode, self.workflow_path

    def _load_workflow_raw(self, workflow_path: Path) -> dict:
        return json.loads(workflow_path.read_text(encoding="utf-8"))

    @staticmethod
    def _workflow_diagnostics(workflow: dict) -> dict:
        checkpoints: list[str] = []
        denoise: list[float] = []
        conditioning_strength: list[float] = []
        for node in workflow.values():
            class_type = node.get("class_type")
            inputs = node.get("inputs", {})
            if class_type in {"CheckpointLoaderSimple", "UNETLoader"}:
                for key in ("ckpt_name", "unet_name", "model_name"):
                    value = inputs.get(key)
                    if isinstance(value, str):
                        checkpoints.append(value)
            if class_type == "KSampler" and isinstance(inputs.get("denoise"), (int, float)):
                denoise.append(float(inputs["denoise"]))
            for key in ("weight", "conditioning_to_strength", "guidance"):
                value = inputs.get(key)
                if isinstance(value, (int, float)):
                    conditioning_strength.append(float(value))
        return {
            "checkpoints": checkpoints,
            "denoise": denoise,
            "conditioning_strength": conditioning_strength,
        }

    def _log_diagnostics(self, workflow_path: Path, workflow: dict, mode: str) -> None:
        diagnostics = self._workflow_diagnostics(workflow)
        _LOGGER.info(
            "Product scene workflow selected: workflow=%s mode=%s model=%s "
            "checkpoint=%s denoise=%s conditioning_strength=%s",
            workflow_path,
            mode,
            self.model_key or "legacy-sd15",
            diagnostics["checkpoints"] or "none",
            diagnostics["denoise"] or "none",
            diagnostics["conditioning_strength"] or "none",
        )

    def _build_workflow(
        self,
        workflow_path: Path,
        prompt: str,
        preset: str,
        image_name: str,
        mask_name: str | None,
        require_mask: bool,
        mode: str = "",
        seg_prompt: str | None = None,
        exclude_prompt: str | None = None,
        parse_class: str | None = None,
        pose_skeleton_name: str | None = None,
    ) -> dict:
        workflow = self._load_workflow_raw(workflow_path)
        style = _PRESET_STYLES.get(preset, _PRESET_STYLES["studio"])
        # Append the mode-specific enhancement (Phase C9) so the prompt steers
        # the workflow without changing brand/brief context handling.
        mode_style = _MODE_STYLES.get(mode, "")
        effective_prompt = f"{prompt}, {mode_style}" if mode_style else prompt
        injected_prompt = injected_image = injected_mask = injected_seg = False
        injected_exclude = injected_parse = injected_skeleton = False
        for node in workflow.values():
            inputs = node.get("inputs", {})
            if inputs.get("parse_class") == PARSE_CLASS_PLACEHOLDER:
                inputs["parse_class"] = parse_class or "Upper-clothes"
                injected_parse = True
            for text_key in ("text", "prompt", "clip_l", "clip_g", "t5xxl", "llama"):
                text = inputs.get(text_key)
                # Auto-seg target / exclusion go into GroundingDINO prompts; check
                # these first so they aren't touched by the __PROMPT__ pass.
                if isinstance(text, str) and EXCLUDE_PROMPT_PLACEHOLDER in text:
                    inputs[text_key] = text.replace(
                        EXCLUDE_PROMPT_PLACEHOLDER, (exclude_prompt or "").strip()
                    )
                    injected_exclude = True
                elif isinstance(text, str) and SEG_PROMPT_PLACEHOLDER in text:
                    inputs[text_key] = text.replace(
                        SEG_PROMPT_PLACEHOLDER, (seg_prompt or "").strip()
                    )
                    injected_seg = True
                elif isinstance(text, str) and PROMPT_PLACEHOLDER in text:
                    inputs[text_key] = text.replace(
                        PROMPT_PLACEHOLDER, effective_prompt
                    ).replace(PRESET_PLACEHOLDER, style)
                    injected_prompt = True
            if (
                node.get("class_type") == "LoadImage"
                and inputs.get("image") == PRODUCT_IMAGE_PLACEHOLDER
            ):
                inputs["image"] = image_name
                injected_image = True
            if (
                mask_name is not None
                and inputs.get("image") == PRODUCT_MASK_PLACEHOLDER
            ):
                inputs["image"] = mask_name
                injected_mask = True
            if (
                pose_skeleton_name is not None
                and inputs.get("image") == POSE_SKELETON_PLACEHOLDER
            ):
                inputs["image"] = pose_skeleton_name
                injected_skeleton = True
            if node.get("class_type") == "KSampler" and "seed" in inputs:
                inputs["seed"] = random.randint(0, 2**32 - 1)
        if not injected_prompt:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{PROMPT_PLACEHOLDER}' text node."
            )
        if not injected_image:
            raise RuntimeError(
                f"Workflow {workflow_path} has no LoadImage node with "
                f"image='{PRODUCT_IMAGE_PLACEHOLDER}'."
            )
        if require_mask and not injected_mask:
            raise RuntimeError(
                f"Workflow {workflow_path} has no mask node with "
                f"image='{PRODUCT_MASK_PLACEHOLDER}' to inject the product mask."
            )
        if seg_prompt and not injected_seg:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{SEG_PROMPT_PLACEHOLDER}' node "
                "to inject the auto-seg target attribute."
            )
        if exclude_prompt and not injected_exclude:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{EXCLUDE_PROMPT_PLACEHOLDER}' "
                "node to inject the auto-seg exclusion attribute."
            )
        if parse_class and not injected_parse:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{PARSE_CLASS_PLACEHOLDER}' "
                "node to inject the human-parse class."
            )
        if pose_skeleton_name and not injected_skeleton:
            raise RuntimeError(
                f"Workflow {workflow_path} has no '{POSE_SKELETON_PLACEHOLDER}' "
                "node to inject the pose skeleton."
            )
        return workflow

    # --- ComfyUI calls -------------------------------------------------------
    async def _upload_image(
        self, client: httpx.AsyncClient, local_path: Path
    ) -> str:
        content_type = mimetypes.guess_type(local_path.name)[0] or "image/png"
        files = {"image": (local_path.name, local_path.read_bytes(), content_type)}
        resp = await client.post(
            "/upload/image", files=files, data={"overwrite": "true"}
        )
        resp.raise_for_status()
        body = resp.json()
        name = body.get("name")
        if not name:
            raise RuntimeError("ComfyUI did not return an uploaded image name")
        subfolder = body.get("subfolder")
        return f"{subfolder}/{name}" if subfolder else name

    async def _verify_ipadapter_available(
        self, client: httpx.AsyncClient, workflow_path: Path
    ) -> None:
        required = sorted(
            {
                ct
                for node in self._load_workflow_raw(workflow_path).values()
                if isinstance((ct := node.get("class_type")), str)
                and ct.startswith(_IPADAPTER_NODE_PREFIX)
            }
        )
        if not required:
            raise RuntimeError(
                f"ipadapter mode but workflow {workflow_path} contains no "
                "IPAdapter nodes. Point COMFYUI_PRODUCT_SCENE_IPADAPTER_WORKFLOW_PATH "
                "at an IPAdapter workflow."
            )
        await self._verify_nodes_registered(
            client,
            required,
            "Install the 'ComfyUI_IPAdapter_plus' custom nodes and the "
            "CLIP-vision + IPAdapter model files, then restart ComfyUI. "
            "(Or use COMFYUI_PRODUCT_SCENE_MODE=img2img.)",
        )

    async def _verify_inpaint_available(self, client: httpx.AsyncClient) -> None:
        await self._verify_nodes_registered(
            client,
            list(_INPAINT_REQUIRED_NODES),
            "These are core ComfyUI nodes — update ComfyUI to a version that "
            "provides them, or use COMFYUI_PRODUCT_SCENE_MODE=img2img.",
        )

    async def _verify_segmented_available(
        self, client: httpx.AsyncClient, required: tuple[str, ...] = _SEGMENTED_REQUIRED_NODES
    ) -> None:
        await self._verify_nodes_registered(
            client,
            list(required),
            "Install the RemBG / ComfyUI_essentials nodes and the "
            "u2net_human_seg model, or pick another scene mode.",
        )

    async def _verify_nodes_registered(
        self, client: httpx.AsyncClient, required: list[str], remedy: str
    ) -> None:
        resp = await client.get("/object_info")
        resp.raise_for_status()
        available = resp.json()
        missing = [ct for ct in required if ct not in available]
        if missing:
            raise RuntimeError(
                f"ComfyUI is missing required nodes: {', '.join(missing)}. {remedy}"
            )

    async def _verify_model_workflow_available(
        self, client: httpx.AsyncClient, workflow_path: Path, workflow: dict
    ) -> None:
        required = _MODEL_REQUIRED_NODES.get(self.model_key)
        if not required:
            return

        resp = await client.get("/object_info")
        resp.raise_for_status()
        object_info = resp.json()
        # A requirement may be a single node name, or a tuple of acceptable
        # alternatives (e.g. TextEncodeQwenImageEdit OR TextEncodeQwenImageEditPlus).
        missing_nodes: list[str] = []
        for node in required:
            if isinstance(node, tuple):
                if not any(alt in object_info for alt in node):
                    missing_nodes.append(" or ".join(node))
            elif node not in object_info:
                missing_nodes.append(node)
        if missing_nodes:
            raise RuntimeError(
                f"PRODUCT_SCENE_MODEL={self.model_key} requires ComfyUI nodes "
                f"that are not registered: {', '.join(missing_nodes)}."
            )

        missing_models: list[str] = []
        for node in workflow.values():
            class_type = node.get("class_type")
            inputs = node.get("inputs", {})
            for input_name, loader_name in _LOADER_MODEL_INPUTS.get(class_type, []):
                model_name = inputs.get(input_name)
                if not isinstance(model_name, str) or model_name.startswith("__"):
                    continue
                loader_info = object_info.get(loader_name, {})
                options = (
                    loader_info.get("input", {})
                    .get("required", {})
                    .get(input_name, [[]])[0]
                )
                if isinstance(options, list) and model_name not in options:
                    missing_models.append(
                        f"{model_name} (expected by {loader_name}.{input_name})"
                    )
        if missing_models:
            raise RuntimeError(
                f"PRODUCT_SCENE_MODEL={self.model_key} is selected, but ComfyUI "
                f"does not list required model files: {', '.join(missing_models)}. "
                "Install the official matching model files or select another "
                "PRODUCT_SCENE_MODEL."
            )

    async def _submit(self, client: httpx.AsyncClient, workflow: dict) -> str:
        resp = await client.post("/prompt", json={"prompt": workflow})
        resp.raise_for_status()
        prompt_id = resp.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return a prompt_id")
        return prompt_id

    @staticmethod
    def _queued_prompt_ids(queue: dict, section: str) -> set[str]:
        """Prompt ids in one /queue section. Entries are [index, prompt_id, ...]."""
        found: set[str] = set()
        for item in queue.get(section) or []:
            if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], str):
                found.add(item[1])
            elif isinstance(item, dict) and isinstance(item.get("prompt_id"), str):
                found.add(item["prompt_id"])
        return found

    async def _abandon(self, client: httpx.AsyncClient, prompt_id: str) -> str:
        """Stop a prompt we have stopped waiting for; return what happened.

        Without this, a timed-out render keeps running on the GPU with nobody
        waiting for it, holding VRAM while the next submission stacks on top.

        A blind POST /interrupt would be unsafe: ComfyUI's interrupt takes no
        prompt_id and cancels whatever is currently executing, which may be a
        different job. So delete by id while the prompt is still pending, and
        only interrupt once /queue confirms the running prompt is ours.
        """
        try:
            resp = await client.get("/queue")
            resp.raise_for_status()
            queue = resp.json()
        except Exception:  # noqa: BLE001 - best-effort cleanup, never masks the timeout
            return "could not reach /queue, so it may still be running"
        if not isinstance(queue, dict):
            return "could not read /queue, so it may still be running"

        if prompt_id in self._queued_prompt_ids(queue, "queue_pending"):
            try:
                await client.post("/queue", json={"delete": [prompt_id]})
                return "removed from the pending queue"
            except Exception:  # noqa: BLE001
                return "still pending; delete failed"
        if prompt_id in self._queued_prompt_ids(queue, "queue_running"):
            try:
                await client.post("/interrupt")
                return "interrupted while running"
            except Exception:  # noqa: BLE001
                return "still running; interrupt failed"
        return "no longer queued"

    async def _await_outputs(
        self, client: httpx.AsyncClient, prompt_id: str
    ) -> dict:
        for _ in range(_POLL_MAX_ATTEMPTS):
            resp = await client.get(f"/history/{prompt_id}")
            resp.raise_for_status()
            entry = resp.json().get(prompt_id)
            if entry and entry.get("outputs"):
                return entry["outputs"]
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        budget = int(_POLL_MAX_ATTEMPTS * _POLL_INTERVAL_SECONDS)
        outcome = await self._abandon(client, prompt_id)
        raise TimeoutError(
            f"ComfyUI product scene {prompt_id} timed out after ~{budget}s; "
            f"{outcome}."
        )

    @staticmethod
    def _first_image(outputs: dict) -> dict:
        for node_output in outputs.values():
            images = node_output.get("images")
            if images:
                return images[0]
        raise RuntimeError("No image found in ComfyUI outputs")

    async def _download(self, client: httpx.AsyncClient, image: dict) -> bytes:
        params = {
            "filename": image["filename"],
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
        resp = await client.get("/view", params=params)
        resp.raise_for_status()
        return resp.content

    # --- public API ----------------------------------------------------------
    async def generate(
        self,
        *,
        scene_id: str,
        prompt: str,
        preset: str,
        product_image_url: str,
        mask_image_url: str | None = None,
        seg_prompt: str | None = None,
    ) -> ProductSceneResult:
        effective_mode, workflow_path = self._effective(mask_image_url)
        product_local = self._resolve_local_path(
            product_image_url, label="product image"
        )
        is_inpaint = effective_mode == INPAINT_MODE
        # Auto-seg attribute edit: GroundingDINO+SAM build the mask in-graph from
        # the text target, so no user mask is needed (or injected).
        is_autoseg = (
            self.model_key == "qwen-image-gguf-autoseg"
            and effective_mode == ATTRIBUTE_EDIT_MODE
        )
        is_humanparse = (
            self.model_key == "qwen-image-gguf-humanparse"
            and effective_mode == ATTRIBUTE_EDIT_MODE
        )
        seg_text: str | None = None
        exclude_text: str | None = None
        parse_class: str | None = None
        if effective_mode == ATTRIBUTE_EDIT_MODE:
            _LOGGER.warning(ATTRIBUTE_EDIT_MASK_WARNING)
            if is_humanparse:
                parse_class = resolve_parse_class(seg_prompt)
                if not parse_class or parse_class == PARSE_MANUAL:
                    raise RuntimeError(
                        "attribute_edit human-parse needs a mappable "
                        "target_attribute (pants, shoes, face, hair, dress, "
                        "jacket/coat)."
                    )
            elif is_autoseg:
                if not seg_prompt:
                    raise RuntimeError(
                        "attribute_edit auto-seg requires a target_attribute "
                        "(e.g. 'pants', 'hair') to segment."
                    )
                seg_text, exclude_text = resolve_seg(seg_prompt)
            elif not mask_image_url:
                # Manual masked editor: a mask is mandatory, no silent fallback.
                if resolve_parse_class(seg_prompt) == PARSE_MANUAL:
                    raise RuntimeError(AMBIGUOUS_GARMENT_WARNING)
                raise RuntimeError(
                    "attribute_edit requires a mask (auto-segmented or "
                    "user-supplied) that marks the region to change."
                )
        # Pose Studio: the pose comes from a preset skeleton (seg_prompt names it)
        # or an uploaded reference photo (mask_image_url). No product mask.
        pose_skeleton_url: str | None = None
        if effective_mode in {POSE_EDIT_MODE, POSE_STYLIZED_MODE}:
            if seg_prompt:
                pose_skeleton_url = f"/storage/pose_presets/{seg_prompt}.png"
            elif mask_image_url:
                pose_skeleton_url = mask_image_url
            else:
                raise RuntimeError(
                    f"{effective_mode} requires a preset (target_attribute) or "
                    "a pose reference image."
                )
            seg_text = None  # the preset name is not a GroundingDINO seg prompt
        # Auto-seg and human-parse build their own masks in-graph.
        needs_mask = effective_mode == INPAINT_MODE or (
            effective_mode == ATTRIBUTE_EDIT_MODE
            and not is_autoseg
            and not is_humanparse
        )
        mask_local = (
            self._resolve_local_path(mask_image_url, label="edit mask")
            if needs_mask
            else None
        )

        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=_HTTP_TIMEOUT_SECONDS
        ) as client:
            workflow_has_ipadapter = any(
                isinstance(node.get("class_type"), str)
                and node.get("class_type", "").startswith(_IPADAPTER_NODE_PREFIX)
                for node in self._load_workflow_raw(workflow_path).values()
            )
            if effective_mode == IPADAPTER_MODE or workflow_has_ipadapter:
                await self._verify_ipadapter_available(client, workflow_path)
            elif is_inpaint:
                await self._verify_inpaint_available(client)
            elif effective_mode == SEGMENTED_COMPOSITE_MODE:
                await self._verify_segmented_available(client)
            elif effective_mode == SEGMENTED_COMPOSITE_POLISHED_MODE:
                await self._verify_segmented_available(
                    client, _SEGMENTED_POLISHED_REQUIRED_NODES
                )

            image_name = await self._upload_image(client, product_local)
            mask_name = (
                await self._upload_image(client, mask_local) if mask_local else None
            )
            skeleton_name = None
            if pose_skeleton_url:
                skeleton_local = self._resolve_local_path(
                    pose_skeleton_url, label="pose skeleton"
                )
                skeleton_name = await self._upload_image(client, skeleton_local)
            workflow = self._build_workflow(
                workflow_path,
                prompt,
                preset,
                image_name,
                mask_name,
                require_mask=needs_mask,
                mode=effective_mode,
                seg_prompt=seg_text,
                exclude_prompt=exclude_text,
                parse_class=parse_class,
                pose_skeleton_name=skeleton_name,
            )
            self._log_diagnostics(workflow_path, workflow, effective_mode)
            await self._verify_model_workflow_available(client, workflow_path, workflow)
            prompt_id = await self._submit(client, workflow)
            outputs = await self._await_outputs(client, prompt_id)
            image = self._first_image(outputs)
            data = await self._download(client, image)

        output_dir = STORAGE_DIR / "product-scenes"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{scene_id}.png"
        (output_dir / filename).write_bytes(data)
        return ProductSceneResult(result_url=f"/storage/product-scenes/{filename}")

    async def preview_mask(
        self,
        *,
        preview_id: str,
        product_image_url: str,
        parse_class: str | None = None,
        seg_prompt: str | None = None,
    ) -> str:
        """Run a segmentation-only workflow (self.workflow_path) and save the
        resulting mask image. Returns the /storage URL. No Qwen edit runs."""
        product_local = self._resolve_local_path(
            product_image_url, label="product image"
        )
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=_HTTP_TIMEOUT_SECONDS
        ) as client:
            image_name = await self._upload_image(client, product_local)
            workflow = self._load_workflow_raw(self.workflow_path)
            for node in workflow.values():
                inputs = node.get("inputs", {})
                if (
                    node.get("class_type") == "LoadImage"
                    and inputs.get("image") == PRODUCT_IMAGE_PLACEHOLDER
                ):
                    inputs["image"] = image_name
                if inputs.get("parse_class") == PARSE_CLASS_PLACEHOLDER:
                    inputs["parse_class"] = parse_class or "Upper-clothes"
                if inputs.get("prompt") == SEG_PROMPT_PLACEHOLDER:
                    inputs["prompt"] = (seg_prompt or "").strip()
            prompt_id = await self._submit(client, workflow)
            outputs = await self._await_outputs(client, prompt_id)
            image = self._first_image(outputs)
            data = await self._download(client, image)
        output_dir = STORAGE_DIR / "mask-previews"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{preview_id}.png"
        (output_dir / filename).write_bytes(data)
        return f"/storage/mask-previews/{filename}"
