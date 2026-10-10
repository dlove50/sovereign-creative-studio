"""Director templates: the kinds of video Sovereign can direct from a short brief.

Each template says what to ask for (brief fields), how long the video may be, which way up
it is, how the story planner should structure it, and what the soundtrack should feel like.
The planner, clip generator, narration and music steps are shared (see director.py).
"""
from __future__ import annotations

from typing import Any

MAX_FIELD_CHARS = 600


def _field(field_id: str, label: str, placeholder: str, *, required: bool = True, long: bool = False) -> dict[str, Any]:
    return {"id": field_id, "label": label, "placeholder": placeholder, "required": required, "long": long}


def _template(
    template_id: str, label: str, tagline: str, *, portrait: bool, seconds: tuple[int, int, int], fields: list[dict[str, Any]],
    structure: str, music: str | None, narration: bool, badge: str | None = None, series: bool = False,
) -> dict[str, Any]:
    low, default, high = seconds
    return {
        "id": template_id, "label": label, "tagline": tagline, "orientation": "portrait" if portrait else "landscape",
        "seconds": {"min": low, "default": default, "max": high}, "fields": fields, "structure": structure,
        "music": music, "narration": narration, "badge": badge, "series": series,
        "image": f"/sovereign-ui/director/{template_id}.webp",
    }


TEMPLATES: list[dict[str, Any]] = [
    _template(
        "short-film", "Short Film", "A small story with a beginning, a turn and an ending.", portrait=False, seconds=(30, 60, 120),
        fields=[_field("story", "What happens?", "A lighthouse keeper finds a message in a bottle that changes the night.", long=True),
                _field("mood", "Mood and look", "quiet, moody, teal and amber light", required=False)],
        structure="A cinematic short film with three acts: set up the world and the character in the first shots, put a clear problem or discovery in the middle, "
                  "and land a satisfying ending image. Favour visual storytelling over talking. Use few characters.",
        music="cinematic, emotional, strings and piano, slow build", narration=False, badge="New"),
    _template(
        "music-video", "Music Video", "Pictures that move with a song.", portrait=False, seconds=(60, 120, 180),
        fields=[_field("song", "What is the song about?", "A summer road trip with the windows down.", long=True),
                _field("genre", "Genre", "reggae pop", required=False),
                _field("look", "Visual style", "sun-soaked, film grain, warm colours", required=False)],
        structure="A music video: a performer and an evocative world cut to the beat. Alternate performance shots (singing to camera, instruments, dancing) with "
                  "story or mood shots that illustrate the theme. Quick, rhythmic cuts and strong colour. No narration and no spoken dialogue.",
        music="__from_brief__", narration=False, badge="New"),
    _template(
        "real-estate", "Real Estate", "Walk buyers through a home they will want to see.", portrait=False, seconds=(20, 45, 90),
        fields=[_field("property", "The property", "Three-bedroom family home with a big garden and a renovated kitchen.", long=True),
                _field("highlights", "Best features", "open-plan living, sunny garden, quiet street", required=False),
                _field("cta", "Call to action", "Book a viewing this weekend.", required=False)],
        structure="A real estate listing tour: begin with an inviting exterior, move room by room (living space, kitchen, bedrooms, outdoor area), "
                  "emphasise light, space and the best features, and end with the exterior at golden hour. Smooth, slow camera moves (glides, pans). "
                  "Short warm narration lines describe each space and finish with the call to action.",
        music="warm acoustic, uplifting, light percussion", narration=True, badge="New"),
    _template(
        "product-ads", "Product Ads", "Make a product look like it deserves attention.", portrait=False, seconds=(10, 20, 45),
        fields=[_field("product", "Product", "Handmade amber sunglasses.", ),
                _field("benefit", "Why people will want it", "Bold style with all-day comfort and UV protection.", long=True),
                _field("cta", "Call to action", "Order today.", required=False)],
        structure="A short product advert: a striking opening shot of the product, close-ups that show materials and details, the product in use by a happy person, "
                  "and a clean final shot with a call to action. Crisp lighting, confident camera moves, one benefit per shot. Brief punchy narration.",
        music="upbeat, modern, confident pop beat", narration=True, badge="New"),
    _template(
        "ad-remake", "Ad Remake", "Re-imagine an ad you like for your own product.", portrait=False, seconds=(15, 30, 60),
        fields=[_field("reference", "Describe the ad you want to remake", "A fast-paced sneaker ad: close-ups of shoes hitting the pavement, then a hero shot.", long=True),
                _field("product", "Your product", "Trail running shoes from a local shop.")],
        structure="Re-create the structure, pacing and mood of the described advert for the user's own product: same kind of opening, same rhythm of shots, "
                  "same type of closing shot. Never reproduce another company's brand, logo, slogan, characters or exact scenes; invent original visuals and wording.",
        music="energetic, rhythmic, modern", narration=True),
    _template(
        "social-content", "Social Content", "Scroll-stopping vertical clips.", portrait=True, seconds=(10, 20, 45),
        fields=[_field("idea", "What is the post about?", "Three quick tricks to keep your plants alive in winter.", long=True),
                _field("vibe", "Vibe", "fun, fast, bright", required=False)],
        structure="A vertical short for social media: a hook in the first two seconds, a quick payoff every few seconds, bold framing for a phone screen, "
                  "energetic movement and a final shot that makes people want to follow. Very short narration lines.",
        music="catchy, bright, upbeat", narration=True),
    _template(
        "ugc-ads", "UGC Ads", "Authentic creator-style ads.", portrait=True, seconds=(10, 20, 40),
        fields=[_field("product", "Product", "A refillable glass water bottle.", ),
                _field("pitch", "What the creator should say", "I switched six months ago and I have not bought plastic since.", long=True)],
        structure="A user-generated-content style advert, filmed as if by an everyday creator on a phone: a relatable hook, the creator holding or using the product in a real setting "
                  "(kitchen, car, bedroom, street), an honest personal reason it works, and a friendly closing recommendation. Handheld, natural light, casual first-person narration.",
        music="light, friendly, subtle lo-fi beat", narration=True),
    _template(
        "micro-drama", "Micro Drama", "Short episodes you can keep going.", portrait=True, seconds=(45, 75, 90),
        fields=[_field("premise", "The story premise", "A night-shift nurse discovers her new neighbour is the stranger who saved her years ago.", long=True),
                _field("tone", "Genre and tone", "romantic drama with a twist", required=False)],
        structure="One episode of a vertical micro drama: open on a gripping moment, introduce or reintroduce the two or three main characters with a clear want, escalate "
                  "with a reveal or confrontation, and end on a cliffhanger. Emotional close-ups, expressive dialogue in short lines, tight scenes in few locations.",
        music="tense, emotional, modern cinematic underscore", narration=False, series=True),
    _template(
        "brand-film", "Brand Film", "Tell the story behind a brand.", portrait=False, seconds=(30, 60, 120),
        fields=[_field("brand", "Brand and what it makes", "A small ceramics studio making everyday mugs and bowls by hand.", long=True),
                _field("values", "What it stands for", "craft, patience, things made to last", required=False)],
        structure="A brand film: open with an emotional image of craft or people, show the process and the people behind it in documentary-style shots, "
                  "express the brand's values through visuals, and close on the product in everyday life with the brand's promise. Calm voice-over, no hard selling.",
        music="warm, organic, acoustic guitar and soft piano", narration=True),
    _template(
        "explainer", "Explainer", "Make one idea easy to understand.", portrait=False, seconds=(30, 60, 120),
        fields=[_field("topic", "Topic", "How solar panels turn sunlight into electricity.", long=True),
                _field("audience", "Who is it for?", "curious teenagers", required=False)],
        structure="An explainer video: state the question, then explain it in three simple steps with a clear visual for each (diagrams, simple animated scenes, everyday examples), "
                  "recap in one sentence and end with what to remember. Friendly, clear narration in short sentences.",
        music="light, curious, playful marimba and soft beat", narration=True, badge=None),
    _template(
        "film-trailer", "Film Trailer", "Hype for a film that does not exist yet.", portrait=False, seconds=(30, 60, 90),
        fields=[_field("premise", "The film", "In a flooded future city, a courier carries the last seed to the surface.", long=True),
                _field("genre", "Genre", "sci-fi thriller", required=False),
                _field("title", "Title card", "The Last Seed", required=False)],
        structure="A film trailer: slow atmospheric opening, introduce the world and the hero, build the conflict with rising intensity and quick cuts, a few big moments of action or emotion, "
                  "then a final title shot. Short dramatic voice-over lines in the style of a trailer announcer, no real actor, studio or franchise names.",
        music="epic cinematic trailer, building percussion and brass, tension then impact", narration=True),
    _template(
        "promo-video", "Promo video", "Announce an offer, launch or event.", portrait=False, seconds=(15, 30, 60),
        fields=[_field("offer", "What are you promoting?", "Grand opening of a neighbourhood bakery this Saturday.", long=True),
                _field("cta", "Call to action", "Come by for a free pastry.", required=False)],
        structure="A promotional video: an attention-grabbing opening, what it is and why it matters in two or three bright shots, the offer or date, and a clear call to action at the end. "
                  "Energetic pacing, vivid colour, friendly narration.",
        music="upbeat, bright, feel-good", narration=True),
]

_BY_ID = {t["id"]: t for t in TEMPLATES}


class TemplateError(ValueError):
    pass


def get_template(template_id: str) -> dict[str, Any]:
    try:
        return _BY_ID[template_id]
    except KeyError as exc:
        raise TemplateError("Unknown template.") from exc


def clean_brief(template: dict[str, Any], brief: dict[str, Any] | None) -> dict[str, str]:
    """Keep only the template's own fields, trimmed; the required ones must be filled in."""
    brief = brief or {}
    cleaned: dict[str, str] = {}
    for field in template["fields"]:
        value = " ".join(str(brief.get(field["id"]) or "").split())[:MAX_FIELD_CHARS]
        if field["required"] and not value:
            raise TemplateError(f"Please fill in: {field['label']}")
        if value:
            cleaned[field["id"]] = value
    return cleaned


def music_style(template: dict[str, Any], brief: dict[str, str]) -> str | None:
    """Soundtrack style for Music Lab, or None when the template has no music."""
    style = template["music"]
    if style == "__from_brief__":
        genre = brief.get("genre") or "pop"
        return f"{genre}, catchy, full band, strong rhythm, instrumental backing"
    return style


def compose_prompt(
    template: dict[str, Any], brief: dict[str, str], series_context: str | None = None, seconds: int | None = None,
    script: str = "",
) -> str:
    """The story request handed to the cinematic planner."""
    lines = [f"Video type: {template['label']}.", template["structure"]]
    if seconds:
        fewest, most = max(1, round(seconds / 8)), max(1, seconds // 3)
        lines.append(f"Use between {fewest} and {max(fewest, most)} shots; every shot lasts 3 to 8 seconds, never less than 3.")
    if template["orientation"] == "portrait":
        lines.append("The video is vertical (9:16): frame subjects for a phone screen.")
    for field in template["fields"]:
        if field["id"] in brief:
            lines.append(f"{field['label']}: {brief[field['id']]}")
    if template["narration"]:
        lines.append("Give every shot a short narration line (one or two sentences) that fits its duration.")
    else:
        lines.append("Use no narration; tell the story with pictures and, where natural, short dialogue.")
    if series_context:
        lines.append(series_context)
    script = "\n".join(line.rstrip() for line in (script or "").strip().splitlines())[:8000]
    if script:
        lines.append("Follow this chapter script closely: one or more shots per chapter, in order. Repeat the look, every "
                     "character's identity and wardrobe, and the rules from its bible inside every shot's prompts so the "
                     "people never change. Script:\n" + script)
    lines.append("Invent original characters, places and wording. Do not use real people, brands, logos or franchises.")
    return "\n".join(lines)
