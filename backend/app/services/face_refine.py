"""Face / subject refinement (architecture placeholder).

Planned pipeline: generate -> detect face/subject -> inpaint/refine that region ->
upscale. This fixes the failures a better base model alone cannot (crooked eyes,
warped mouths, weak dog snouts, bad hands, anime face errors, blurry small faces).

Not implemented in this pass: readiness reports "coming soon" and the UI exposes a
disabled control. When the detector + refine workflow are installed and
FACE_REFINE_ENABLED=true, this becomes available. Nothing is faked meanwhile.
"""
from __future__ import annotations

from pathlib import Path

from .. import config


def refine_readiness() -> dict:
    workflow_path = Path(config.IMAGE_WORKFLOW_FACE_REFINE)
    workflow_present = (
        workflow_path if workflow_path.is_absolute() else config.BASE_DIR / workflow_path
    ).is_file()
    available = config.FACE_REFINE_ENABLED and workflow_present
    if available:
        detail = "Face / subject refinement is ready."
    elif not config.FACE_REFINE_ENABLED:
        detail = "Face / Subject Refine — coming soon."
    else:
        detail = "Refinement workflow not installed yet."
    return {
        "available": available,
        "enabled": config.FACE_REFINE_ENABLED,
        "workflow_present": workflow_present,
        "detail": detail,
    }
