"""Shared schema literals used across API domains."""
from typing import Literal

MediaType = Literal["image", "video"]
ProductScenePreset = Literal["studio", "luxury", "outdoor", "social ad"]
ProductSceneMode = Literal[
    "img2img",
    "ipadapter",
    "inpaint",
    "segmented_composite",
    "segmented_composite_polished",
    "advertising_scene",
    "fashion_editorial",
    "creative_fashion_edit",
    "creative_edit",
    "character_reimagination",
    "fashion_transformation",
    "cinematic_scene_builder",
    "clothing_style_edit",
    "pose_edit",
    "pose_stylized",
    "film_scene",
    "attribute_edit",
]
CopyType = Literal[
    "product_description",
    "instagram_caption",
    "facebook_ad",
    "tiktok_hook",
    "seo_title",
]
CopyTone = Literal["luxury", "friendly", "bold", "professional", "playful"]
VideoMotionPreset = Literal[
    "slow_zoom",
    "orbit",
    "handheld",
    "product_reveal",
    "product_motion",
    "cinematic_push",
    "runway_walk",
    "parallax",
    "dolly_in",
    "subtle_breathing",
]
CampaignType = Literal[
    "product_launch",
    "ecommerce",
    "social_media",
    "fashion_editorial",
    "luxury_brand",
    "custom",
]
FamilyUserRole = Literal["owner_admin", "family_user", "guest"]
FamilyUserStatus = Literal["active", "disabled"]
CreditTransactionType = Literal[
    "generation_charge",
    "refund",
    "manual_add",
    "manual_remove",
    "adjustment",
    "sandbox_topup",
]
CreditTransactionStatus = Literal["completed", "failed", "refunded", "manual"]
