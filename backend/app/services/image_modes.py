"""Image Quality Modes.

A mode bundles three things so non-technical users get good results from a single
choice: (1) a recommended local model with a graceful fallback chain, (2) a prompt
enhancer tuned for that subject (faces, animals, product, anime, cartoon, ...),
and (3) readiness + subject-size guidance. Modes never hard-block: the effective
model is the best *ready* one in the preference list, and `local_fast` is always
ready, so the safe local default is preserved. Nothing is faked.
"""
from __future__ import annotations

from . import image_presets

# Each mode: preference list of preset ids (best first), a prompt enhancer, the
# human-readable recommended model, whether to show subject-size guidance, and
# whether face/subject refinement applies (architecture only for now).
_MODES = [
    {
        "id": "realistic_general",
        "label": "Realistic / General",
        "description": "General high-quality local images, realistic scenes, everyday prompts.",
        "recommended_model": "FLUX.1 Krea Dev FP8",
        "presets": ["flux1_krea", "flux2_klein", "krea2_turbo_fp8", "flux1_dev", "sdxl", "local_fast"],
        "enhancer": "high detail, sharp focus, natural lighting, realistic, true-to-life colors",
        "subject_guidance": False,
    },
    {
        "id": "portrait_human",
        "label": "Portrait / Human Face",
        "description": "People and faces with correct anatomy and detail.",
        "recommended_model": "FLUX.1 Krea Dev FP8",
        "presets": ["flux1_krea", "krea2_turbo_fp8", "flux1_dev", "sdxl", "local_fast"],
        "enhancer": (
            "realistic human facial anatomy, symmetrical eyes, natural skin texture with fine detail, "
            "clear sharp face, the face is large and prominent in the frame, professional portrait "
            "lighting, shallow depth of field, photorealistic"
        ),
        "subject_guidance": True,
    },
    {
        "id": "animal_pet",
        "label": "Animal / Pet Portrait",
        "description": "Pets and animals with the face as the clear main subject.",
        "recommended_model": "FLUX.1 Krea Dev FP8",
        "presets": ["flux1_krea", "flux2_klein", "krea2_turbo_fp8", "flux1_dev", "sdxl", "local_fast"],
        "enhancer": (
            "the animal is the main subject and fills 35-45% of the image, clear face clearly visible, "
            "realistic animal facial anatomy, symmetrical eyes, natural muzzle proportions, detailed fur "
            "around the face, sharp focus on the face; not a tiny distant animal and not a wide empty landscape"
        ),
        "subject_guidance": True,
    },
    {
        "id": "krea2_turbo_fp8",
        "label": "Krea 2 Turbo FP8 — Local",
        "description": "Direct selection of Krea 2 Turbo FP8. Photorealistic quality; bypasses the fallback chain so Krea 2 is always the active model when installed.",
        "recommended_model": "Krea 2 Turbo FP8 — Local",
        "presets": ["krea2_turbo_fp8", "local_fast"],
        "enhancer": "high detail, sharp focus, natural lighting, realistic, true-to-life colors, photorealistic",
        "subject_guidance": False,
    },
    {
        "id": "product_shot",
        "label": "Product Shot",
        "description": "Product hero images, studio lighting, clean backgrounds.",
        "recommended_model": "FLUX / FLUX-Kontext product workflow",
        "presets": ["flux1_dev", "flux2_klein", "sdxl", "local_fast"],
        "enhancer": (
            "professional product hero shot, studio lighting, clean seamless background, sharp focus, "
            "high detail, commercial product photography"
        ),
        "subject_guidance": False,
    },
    {
        "id": "anime_illustration",
        "label": "Anime / Illustration",
        "description": "Anime and illustration. Best with a dedicated anime checkpoint.",
        "recommended_model": "Illustrious XL (anime SDXL)",
        "presets": ["illustrious_xl", "netayume_anime", "sdxl", "local_fast"],
        "enhancer": (
            "high quality anime illustration, clean line art, cel shading, vibrant colors, "
            "detailed expressive eyes, polished anime artwork"
        ),
        "subject_guidance": False,
    },
    {
        "id": "cartoon_3d",
        "label": "Cartoon / 3D Character",
        "description": "Family-friendly cartoon and stylized 3D characters (Pixar-like, children's book).",
        "recommended_model": "FLUX.2 Klein 4B (or stylized SDXL)",
        "presets": ["flux2_klein", "flux1_dev", "sdxl", "local_fast"],
        "enhancer": (
            "stylized 3D character render, Pixar-like family-friendly animation style, soft global "
            "illumination, expressive friendly features, smooth clean shapes, colorful, high detail, "
            "children's book illustration friendliness"
        ),
        "subject_guidance": False,
    },
    {
        "id": "fallback",
        "label": "Fallback (SDXL)",
        "description": "Stable SDXL Base + Refiner fallback when Flux is unavailable or too slow.",
        "recommended_model": "SDXL Base + Refiner",
        "presets": ["sdxl", "local_fast"],
        "enhancer": "high quality, sharp focus, detailed",
        "subject_guidance": False,
    },
]

_MODE_BY_ID = {m["id"]: m for m in _MODES}

DEFAULT_MODE = "realistic_general"
_SUBJECT_GUIDANCE = (
    "Small or distant faces may distort. For best face quality, make the subject large "
    "in the frame (a close or medium shot rather than a wide landscape)."
)


def is_known_mode(mode_id: str | None) -> bool:
    return bool(mode_id) and mode_id in _MODE_BY_ID


def _effective_preset(mode: dict, ready: dict[str, bool]) -> str:
    for preset_id in mode["presets"]:
        if ready.get(preset_id):
            return preset_id
    return image_presets.DEFAULT_PRESET  # local_fast is always available


def effective_preset(mode_id: str | None) -> str:
    mode = _MODE_BY_ID.get(mode_id or DEFAULT_MODE, _MODE_BY_ID[DEFAULT_MODE])
    ready = {p: image_presets.preset_ready(p) for p in mode["presets"]}
    return _effective_preset(mode, ready)


def apply_mode_prompt(prompt: str, mode_id: str | None) -> str:
    mode = _MODE_BY_ID.get(mode_id or DEFAULT_MODE)
    if mode is None or not mode["enhancer"]:
        return prompt
    base = prompt.strip().rstrip(",")
    return f"{base}, {mode['enhancer']}" if base else mode["enhancer"]


def _preset_label(preset_id: str) -> str:
    for p in image_presets.list_image_presets():
        if p["id"] == preset_id:
            return p["label"]
    return preset_id


def list_image_modes() -> list[dict]:
    presets = {p["id"]: p for p in image_presets.list_image_presets()}
    out: list[dict] = []
    for mode in _MODES:
        recommended_preset = mode["presets"][0]
        recommended_ready = bool(presets.get(recommended_preset, {}).get("ready"))
        ready_map = {p: bool(presets.get(p, {}).get("ready")) for p in mode["presets"]}
        eff = _effective_preset(mode, ready_map)
        eff_label = presets.get(eff, {}).get("label", eff)
        setup_note = None
        if not recommended_ready:
            setup_note = (
                f"Recommended model ({mode['recommended_model']}) is not installed — "
                f"using {eff_label} for now. Install it for best results."
            )
        out.append(
            {
                "id": mode["id"],
                "label": mode["label"],
                "description": mode["description"],
                "recommended_model": mode["recommended_model"],
                "recommended_ready": recommended_ready,
                "effective_preset": eff,
                "effective_model": eff_label,
                "setup_note": setup_note,
                "subject_size_guidance": _SUBJECT_GUIDANCE if mode["subject_guidance"] else None,
            }
        )
    return out
