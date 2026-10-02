"""Safe Wan InfiniteTalk avatar quality presets.

These are deliberately conservative. Normal users select a named preset only;
raw dimensions and sampler values stay server-controlled through env overrides.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from .. import config


@dataclass(frozen=True)
class AvatarWanPreset:
    id: str
    label: str
    description: str
    width: int
    height: int
    frames: int
    steps: int
    cfg: float
    warning: str | None = None
    verified: bool = False

    def as_public_dict(self, *, default: bool = False) -> dict:
        return {**asdict(self), "default": default}


PRESETS: dict[str, AvatarWanPreset] = {
    "tiny_test": AvatarWanPreset(
        id="tiny_test",
        label="Fast test",
        description="Small validation pass for checking lipsync and app wiring.",
        width=256,
        height=256,
        frames=41,
        steps=2,
        cfg=1.0,
        verified=True,
    ),
    "low_vram": AvatarWanPreset(
        id="low_vram",
        label="Better quality",
        description="Slightly stronger render while staying cautious on 16 GB VRAM.",
        width=320,
        height=320,
        frames=41,
        steps=4,
        cfg=1.0,
        warning="May take longer than Fast test; stop if VRAM pressure appears.",
    ),
    "balanced": AvatarWanPreset(
        id="balanced",
        label="Balanced",
        description="Medium validation tier for short clips after Low VRAM succeeds.",
        width=384,
        height=384,
        frames=61,
        steps=6,
        cfg=1.0,
        warning="Use only after the smaller presets pass on the current ComfyUI session.",
    ),
    "quality": AvatarWanPreset(
        id="quality",
        label="High quality",
        description="Experimental local quality tier. Keep short and expect high VRAM use.",
        width=512,
        height=512,
        frames=81,
        steps=8,
        cfg=1.0,
        warning="Experimental: can OOM or fail on 16 GB VRAM. Failed jobs are not charged.",
    ),
    "portrait_480p": AvatarWanPreset(
        id="portrait_480p",
        label="Vertical 480p",
        description="Phone-shaped 480x832 for Reels/Shorts. Long scripts render in 3-second chunks.",
        width=480,
        height=832,
        frames=81,
        steps=6,
        cfg=1.0,
        warning="Best with the lightx2v LoRA set in AVATAR_WAN_LORA_NAME.",
    ),
}


def preset_ids() -> tuple[str, ...]:
    return tuple(PRESETS)


def default_preset_id() -> str:
    preset_id = (config.AVATAR_WAN_PRESET or "tiny_test").strip()
    return preset_id if preset_id in PRESETS else "tiny_test"


def _override_int(value: int | None, current: int, *, minimum: int, maximum: int) -> int:
    if value is None:
        return current
    return max(minimum, min(maximum, int(value)))


def _override_float(value: float | None, current: float, *, minimum: float, maximum: float) -> float:
    if value is None:
        return current
    return max(minimum, min(maximum, float(value)))


def resolve_preset(preset_id: str | None = None) -> AvatarWanPreset:
    resolved_id = (preset_id or default_preset_id()).strip()
    preset = PRESETS.get(resolved_id) or PRESETS["tiny_test"]
    return replace(
        preset,
        width=_override_int(config.AVATAR_WAN_WIDTH, preset.width, minimum=128, maximum=768),
        height=_override_int(config.AVATAR_WAN_HEIGHT, preset.height, minimum=128, maximum=768),
        frames=_override_int(config.AVATAR_WAN_FRAMES, preset.frames, minimum=9, maximum=121),
        steps=_override_int(config.AVATAR_WAN_STEPS, preset.steps, minimum=1, maximum=30),
        cfg=_override_float(config.AVATAR_WAN_CFG, preset.cfg, minimum=1.0, maximum=5.0),
    )


def public_presets() -> list[dict]:
    default_id = default_preset_id()
    return [resolve_preset(preset_id).as_public_dict(default=preset_id == default_id) for preset_id in PRESETS]
