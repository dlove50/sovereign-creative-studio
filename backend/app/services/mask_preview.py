"""Segmentation-only mask preview for the Attribute Editor UI.

Runs just the human-parse / GroundingDINO step (fast, no Qwen edit) so the user
can see the region before committing to a full render. Mock backend returns a
lightweight placeholder so the flow works without ComfyUI.
"""
import asyncio
import uuid

from .. import config
from ..product_scene_generators.comfyui import (
    PARSE_MANUAL,
    ComfyUIProductSceneGenerator,
    resolve_parse_class,
    resolve_seg,
)


def route_for(target_attribute: str | None) -> str:
    cls = resolve_parse_class(target_attribute)
    if cls and cls != PARSE_MANUAL:
        return "human-parse"
    if cls == PARSE_MANUAL:
        return "manual-mask"
    return "groundingdino-sam"


def _placeholder_mask(preview_id: str) -> str:
    out = config.STORAGE_DIR / "mask-previews"
    out.mkdir(parents=True, exist_ok=True)
    name = f"{preview_id}.svg"
    # Mock mask: white region on black (matches the white=edit convention).
    (out / name).write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" '
        'viewBox="0 0 1024 1024"><rect width="1024" height="1024" fill="#000000"/>'
        '<ellipse cx="512" cy="620" rx="230" ry="320" fill="#ffffff"/></svg>',
        encoding="utf-8",
    )
    return f"/storage/mask-previews/{name}"


def build_mask_preview(asset_image_url: str, target_attribute: str | None) -> dict:
    """Return {mask_url, route}. mask_url is None for the manual-mask route
    (the client previews the user-supplied mask itself)."""
    route = route_for(target_attribute)
    preview_id = uuid.uuid4().hex
    if route == "manual-mask":
        return {"mask_url": None, "route": route}
    if config.PRODUCT_SCENE_BACKEND != "comfyui":
        return {"mask_url": _placeholder_mask(preview_id), "route": route}
    if route == "human-parse":
        gen = ComfyUIProductSceneGenerator(
            config.COMFYUI_BASE_URL,
            config.COMFYUI_MASKPREVIEW_HUMANPARSE_WORKFLOW_PATH,
            "attribute_edit",
            model_key="",
        )
        url = asyncio.run(
            gen.preview_mask(
                preview_id=preview_id,
                product_image_url=asset_image_url,
                parse_class=resolve_parse_class(target_attribute),
            )
        )
    else:
        gen = ComfyUIProductSceneGenerator(
            config.COMFYUI_BASE_URL,
            config.COMFYUI_MASKPREVIEW_AUTOSEG_WORKFLOW_PATH,
            "attribute_edit",
            model_key="",
        )
        seg_text, _ = resolve_seg(target_attribute)
        url = asyncio.run(
            gen.preview_mask(
                preview_id=preview_id,
                product_image_url=asset_image_url,
                seg_prompt=seg_text,
            )
        )
    return {"mask_url": url, "route": route}
