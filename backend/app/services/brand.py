from ..models import Project
from ..schemas import BrandKitOut

BRAND_FIELDS = [
    "brand_name",
    "brand_voice",
    "target_audience",
    "primary_colors",
    "style_keywords",
    "negative_keywords",
    "product_positioning",
    "campaign_notes",
]


def project_brand_kit(project: Project) -> BrandKitOut:
    return BrandKitOut(**{field: getattr(project, field) for field in BRAND_FIELDS})


def brand_context(project: Project) -> str | None:
    labels = {
        "brand_name": "Brand",
        "brand_voice": "Voice",
        "target_audience": "Target audience",
        "primary_colors": "Primary colors",
        "style_keywords": "Style keywords",
        "negative_keywords": "Avoid",
        "product_positioning": "Positioning",
        "campaign_notes": "Campaign notes",
    }
    parts = []
    for field in BRAND_FIELDS:
        value = (getattr(project, field) or "").strip()
        if value:
            parts.append(f"{labels[field]}: {value}")
    return "; ".join(parts) or None


def with_brand_context(prompt: str, project: Project) -> str:
    context = brand_context(project)
    if not context:
        return prompt
    return f"{prompt}\n\nBrand guidance: {context}"
