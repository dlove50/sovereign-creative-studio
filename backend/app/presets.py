"""Static, in-code campaign presets.

A preset bundles a product-scene style (preset + recommended mode + prompt
template) with a matching copy type/tone/audience, so a user can launch a
coordinated scene + copy campaign from one click. Kept in code (no DB table) —
they are configuration, not user data.

The scene prompt template uses the ``{product}`` placeholder, filled with the
campaign's product name at launch time.
"""
from dataclasses import dataclass

PRODUCT_PLACEHOLDER = "{product}"


@dataclass(frozen=True)
class CampaignPreset:
    id: str
    name: str
    description: str
    scene_preset: str  # ProductScenePreset value
    scene_mode: str  # ProductSceneMode value (recommended)
    scene_prompt_template: str
    copy_type: str  # CopyType value
    tone: str  # CopyTone value
    audience_hint: str


_PRESETS: dict[str, CampaignPreset] = {
    p.id: p
    for p in [
        CampaignPreset(
            id="luxury_launch",
            name="Luxury Launch",
            description="Premium hero shot with a refined product description.",
            scene_preset="luxury",
            scene_mode="ipadapter",
            scene_prompt_template=(
                "{product} as a premium launch hero, on polished marble with "
                "dramatic rim lighting and elegant negative space"
            ),
            copy_type="product_description",
            tone="luxury",
            audience_hint="discerning, high-end buyers",
        ),
        CampaignPreset(
            id="instagram_product_ad",
            name="Instagram Product Ad",
            description="Bright lifestyle scene with a scroll-stopping caption.",
            scene_preset="social ad",
            scene_mode="img2img",
            scene_prompt_template=(
                "{product} styled for a vibrant Instagram product ad, bright "
                "punchy colors, lifestyle vibe"
            ),
            copy_type="instagram_caption",
            tone="playful",
            audience_hint="gen z and millennial social shoppers",
        ),
        CampaignPreset(
            id="black_friday",
            name="Black Friday",
            description="High-urgency sale scene with a bold Facebook ad.",
            scene_preset="social ad",
            scene_mode="img2img",
            scene_prompt_template=(
                "{product} in a bold Black Friday sale scene, high-contrast "
                "dramatic lighting, sense of urgency"
            ),
            copy_type="facebook_ad",
            tone="bold",
            audience_hint="deal-seeking shoppers ready to buy",
        ),
        CampaignPreset(
            id="minimalist_studio",
            name="Minimalist Studio",
            description="Clean studio shot with a concise SEO title.",
            scene_preset="studio",
            scene_mode="img2img",
            scene_prompt_template=(
                "{product} on a clean seamless studio backdrop, soft even "
                "lighting, minimalist composition"
            ),
            copy_type="seo_title",
            tone="professional",
            audience_hint="online catalog and marketplace shoppers",
        ),
        CampaignPreset(
            id="outdoor_lifestyle",
            name="Outdoor Lifestyle",
            description="Natural outdoor scene with a punchy TikTok hook.",
            scene_preset="outdoor",
            scene_mode="img2img",
            scene_prompt_template=(
                "{product} in a natural outdoor lifestyle setting, golden-hour "
                "daylight, organic environment"
            ),
            copy_type="tiktok_hook",
            tone="friendly",
            audience_hint="active, outdoorsy younger audiences",
        ),
    ]
}


def list_presets() -> list[CampaignPreset]:
    return list(_PRESETS.values())


def get_preset(preset_id: str) -> CampaignPreset | None:
    return _PRESETS.get(preset_id)


def render_scene_prompt(preset: CampaignPreset, product_name: str) -> str:
    return preset.scene_prompt_template.replace(PRODUCT_PLACEHOLDER, product_name)
