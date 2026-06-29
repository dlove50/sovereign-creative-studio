"""Shared prompt construction for LLM copy backends.

Builds chat messages from the structured fields. The user's free text is passed
as labelled *data* (not blended into the instructions), and the system message
pins the format/tone and tells the model to return only the final copy."""

_COPY_TYPE_GUIDE = {
    "product_description": "Write a concise, compelling product description (2-4 sentences).",
    "instagram_caption": "Write an Instagram caption: a hook line, one or two short lines, then 3-5 relevant hashtags.",
    "facebook_ad": "Write a Facebook ad with a short headline, a 1-2 sentence body, and a clear call to action.",
    "tiktok_hook": "Write a single punchy TikTok hook (one or two sentences) designed to stop the scroll.",
    "seo_title": "Write a single SEO title under 60 characters. Output only the title text.",
}

_TONE_GUIDE = {
    "luxury": "refined, aspirational, understated elegance",
    "friendly": "warm, approachable, conversational",
    "bold": "punchy, confident, high-energy",
    "professional": "clear, credible, no-nonsense",
    "playful": "fun, witty, lighthearted",
}


def build_messages(
    *,
    copy_type: str,
    tone: str,
    audience: str | None,
    prompt: str,
    product_context: str | None,
) -> list[dict]:
    type_guide = _COPY_TYPE_GUIDE.get(copy_type, "Write marketing copy.")
    tone_guide = _TONE_GUIDE.get(tone, tone)
    system = (
        "You are an expert e-commerce marketing copywriter. "
        f"{type_guide} Use a {tone} tone ({tone_guide}). "
        "Output only the final copy with no preamble, labels, explanations, or "
        "surrounding quotes."
    )

    audience_text = (audience or "").strip() or "a general shopper audience"
    user_lines = [
        f"Audience: {audience_text}",
        f"Product / context: {prompt.strip()}",
    ]
    if product_context:
        user_lines.append(f"Additional context: {product_context}")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n".join(user_lines)},
    ]


def build_system_and_user(
    *,
    copy_type: str,
    tone: str,
    audience: str | None,
    prompt: str,
    product_context: str | None,
) -> tuple[str, str]:
    """Same content as build_messages, split for APIs (Claude/Gemini) that take a
    separate system instruction and a single user message."""
    messages = build_messages(
        copy_type=copy_type,
        tone=tone,
        audience=audience,
        prompt=prompt,
        product_context=product_context,
    )
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user = next((m["content"] for m in messages if m["role"] == "user"), "")
    return system, user
