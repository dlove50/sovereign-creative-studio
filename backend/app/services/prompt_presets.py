"""Prompt style presets — reusable framing appended to the user's prompt.

The "Dog / Animal Portrait Quality" preset frames the animal as the main subject
filling the frame and steers away from tiny, distant animals in large landscapes.
"""
from __future__ import annotations

_STYLE_PRESETS: dict[str, dict] = {
    "none": {
        "label": "None",
        "description": "Use the prompt exactly as written.",
        "suffix": "",
    },
    "animal_portrait": {
        "label": "Dog / Animal Portrait Quality",
        "description": "Frames the animal as the main subject, close and detailed — not a tiny animal in a wide landscape.",
        "suffix": (
            "close-up portrait with the animal as the main subject filling most of the frame, "
            "sharp detailed facial features, expressive eyes, detailed fur and whiskers, "
            "shallow depth of field with a softly blurred background, professional pet and "
            "wildlife photography, soft natural lighting, ultra-detailed, photorealistic; "
            "the animal is large and centered in the frame, not a tiny distant animal and "
            "not a wide empty landscape"
        ),
    },
}


def list_style_presets() -> list[dict]:
    return [
        {"id": pid, "label": p["label"], "description": p["description"]}
        for pid, p in _STYLE_PRESETS.items()
    ]


def apply_style_preset(prompt: str, style_id: str | None) -> str:
    preset = _STYLE_PRESETS.get(style_id or "none")
    if preset is None or not preset["suffix"]:
        return prompt
    base = prompt.strip().rstrip(",")
    return f"{base}, {preset['suffix']}" if base else preset["suffix"]
