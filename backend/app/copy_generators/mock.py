"""Mock copy generator: structured, tone-aware templates per copy type.

Deterministic given its inputs (no randomness), so it's easy to test. A real
local LLM / API backend later implements the same CopyGenerator interface.
"""
import asyncio

from .base import CopyGenerator, CopyResult

_SIMULATED_LATENCY_SECONDS = 0.3

# tone -> (adjective, vibe, call-to-action)
_TONE = {
    "luxury": ("exquisite", "refined elegance", "Elevate your everyday."),
    "friendly": ("wonderful", "warm everyday charm", "Come see for yourself!"),
    "bold": ("game-changing", "unapologetic confidence", "Don't blink."),
    "professional": ("reliable", "proven performance", "Get started today."),
    "playful": ("delightful", "fun-loving energy", "Let's play!"),
}


def _tone(tone: str) -> tuple[str, str, str]:
    return _TONE.get(tone, _TONE["professional"])


def _hashtags(tone: str, copy_type: str) -> str:
    base = copy_type.split("_")[0]
    return f"#{base} #{tone} #shopnow"


def build_copy(
    *,
    copy_type: str,
    tone: str,
    audience: str | None,
    prompt: str,
    product_context: str | None,
) -> str:
    adj, vibe, cta = _tone(tone)
    subject = prompt.strip()
    aud = (audience or "").strip() or "your customers"
    ctx = f" {product_context}." if product_context else ""

    if copy_type == "product_description":
        return (
            f"Meet {subject} — {adj} by design and made for {aud}.{ctx} "
            f"Every detail reflects {vibe}, so you get more than a product; "
            f"you get a statement. {cta}"
        )
    if copy_type == "instagram_caption":
        return (
            f"✨ {subject} hits different.\n"
            f"{adj.capitalize()} {vibe} for {aud}.{ctx}\n\n"
            f"{cta}\n{_hashtags(tone, copy_type)}"
        )
    if copy_type == "facebook_ad":
        return (
            f"Headline: {subject} — {adj} for {aud}\n\n"
            f"Body: Built around {vibe}, {subject} is the upgrade {aud} have "
            f"been waiting for.{ctx}\n\n"
            f"👉 {cta}"
        )
    if copy_type == "tiktok_hook":
        return (
            f"POV: you just found {subject}. {adj.capitalize()} energy, zero "
            f"compromise — made for {aud}. Wait for it…"
        )
    if copy_type == "seo_title":
        title = f"{subject} | {adj.capitalize()} Pick for {aud}"
        return title[:60].rstrip(" |")

    # Unknown type: safe generic fallback.
    return f"{subject} — {adj} {vibe} for {aud}. {cta}"


class MockCopyGenerator(CopyGenerator):
    async def generate(
        self,
        *,
        copy_id: str,
        copy_type: str,
        tone: str,
        audience: str | None,
        prompt: str,
        product_context: str | None = None,
    ) -> CopyResult:
        await asyncio.sleep(_SIMULATED_LATENCY_SECONDS)
        return CopyResult(
            result_text=build_copy(
                copy_type=copy_type,
                tone=tone,
                audience=audience,
                prompt=prompt,
                product_context=product_context,
            )
        )
