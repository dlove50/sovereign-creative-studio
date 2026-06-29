"""Mock generator: writes a deterministic SVG placeholder embedding the prompt.

SVG is used so there are zero binary/image dependencies (no Pillow/ffmpeg).
The colors are derived from the prompt hash so each result looks distinct.
A real ComfyUI run will produce PNG/MP4 instead — the API contract is the same."""
import asyncio
import hashlib
import html
import textwrap

from ..config import STORAGE_DIR
from .base import GenerationResult, Generator

_CANVAS = 1024
_SIMULATED_LATENCY_SECONDS = 0.8


def _hex_color(seed: str, salt: str) -> str:
    digest = hashlib.sha256(f"{seed}|{salt}".encode()).hexdigest()
    return f"#{digest[:6]}"


def _wrap(prompt: str) -> list[str]:
    return textwrap.wrap(prompt.strip(), width=26)[:6] or ["(empty prompt)"]


def _build_svg(prompt: str, media_type: str) -> str:
    c1 = _hex_color(prompt, "a")
    c2 = _hex_color(prompt, "b")
    lines = _wrap(prompt)
    line_height = 64
    start_y = _CANVAS / 2 - (len(lines) - 1) * line_height / 2

    text_spans = "".join(
        f'<text x="{_CANVAS / 2}" y="{start_y + i * line_height}" '
        f'text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="44" font-weight="700" fill="#ffffff" '
        f'opacity="0.96">{html.escape(line)}</text>'
        for i, line in enumerate(lines)
    )

    play_badge = ""
    if media_type == "video":
        play_badge = (
            f'<circle cx="{_CANVAS / 2}" cy="{_CANVAS - 150}" r="48" '
            f'fill="#ffffff" opacity="0.92"/>'
            f'<polygon points="{_CANVAS / 2 - 16},{_CANVAS - 174} '
            f'{_CANVAS / 2 - 16},{_CANVAS - 126} {_CANVAS / 2 + 26},{_CANVAS - 150}" '
            f'fill="{c1}"/>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{_CANVAS}" height="{_CANVAS}" viewBox="0 0 {_CANVAS} {_CANVAS}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{c1}"/>
      <stop offset="100%" stop-color="{c2}"/>
    </linearGradient>
  </defs>
  <rect width="{_CANVAS}" height="{_CANVAS}" fill="url(#bg)"/>
  <rect width="{_CANVAS}" height="{_CANVAS}" fill="#000000" opacity="0.28"/>
  <text x="48" y="80" font-family="Segoe UI, Arial, sans-serif" font-size="30"
        font-weight="700" fill="#ffffff" opacity="0.85">Sovereign Creative Studio</text>
  <text x="48" y="120" font-family="Segoe UI, Arial, sans-serif" font-size="22"
        fill="#ffffff" opacity="0.6">mock {html.escape(media_type)} preview</text>
  {text_spans}
  {play_badge}
</svg>
"""


class MockGenerator(Generator):
    async def generate(
        self,
        *,
        generation_id: str,
        prompt: str,
        media_type: str,
        mode: str = "text_to_image",
        source_image_url: str | None = None,
    ) -> GenerationResult:
        await asyncio.sleep(_SIMULATED_LATENCY_SECONDS)
        filename = f"{generation_id}.svg"
        (STORAGE_DIR / filename).write_text(
            _build_svg(prompt, media_type), encoding="utf-8"
        )
        return GenerationResult(file_url=f"/storage/{filename}")
