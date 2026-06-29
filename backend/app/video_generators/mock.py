"""Mock video generator.

Producing a real .mp4 needs ffmpeg/model weights, so the mock writes a
self-contained animated HTML artifact instead: the source image with a CSS
motion matching the preset. It's viewable in a browser/iframe and downloadable.
A real backend later returns an actual video file behind the same interface.
"""
import asyncio
import html

from ..config import STORAGE_DIR
from .base import VideoGenerator, VideoResult

_SIMULATED_LATENCY_SECONDS = 0.5

# motion preset -> (CSS @keyframes body, animation timing/iteration)
_MOTION = {
    "slow_zoom": (
        "from { transform: scale(1); } to { transform: scale(1.15); }",
        "ease-in-out infinite alternate",
    ),
    "orbit": (
        "from { transform: rotate(-4deg) scale(1.08); } to { transform: rotate(4deg) scale(1.08); }",
        "ease-in-out infinite alternate",
    ),
    "handheld": (
        "0% { transform: translate(0,0); } 25% { transform: translate(-1%,1%); } "
        "50% { transform: translate(1%,-1%); } 75% { transform: translate(-1%,-1%); } "
        "100% { transform: translate(0,0); }",
        "ease-in-out infinite",
    ),
    "product_reveal": (
        "from { opacity: 0; transform: scale(1.2); } to { opacity: 1; transform: scale(1); }",
        "ease-out forwards",
    ),
    "product_motion": (
        "0% { opacity: .92; transform: translateX(-5%) scale(1.08) rotate(-1deg); } "
        "35% { opacity: 1; transform: translateX(3%) scale(1.16) rotate(1deg); } "
        "70% { opacity: 1; transform: translateX(-2%) scale(1.12) rotate(0deg); } "
        "100% { opacity: .96; transform: translateX(5%) scale(1.18) rotate(1.5deg); }",
        "ease-in-out infinite alternate",
    ),
    "cinematic_push": (
        "0% { transform: scale(1.02) translateY(1%); filter: contrast(1); } "
        "100% { transform: scale(1.2) translateY(-1%); filter: contrast(1.08); }",
        "cubic-bezier(.2,.7,.2,1) infinite alternate",
    ),
    "runway_walk": (
        "0% { transform: translateX(-4%) scale(1.08); } "
        "45% { transform: translateX(1%) scale(1.15); } "
        "100% { transform: translateX(5%) scale(1.12); }",
        "ease-in-out infinite alternate",
    ),
    "parallax": (
        "0% { transform: translate(-3%, 1%) scale(1.12); } "
        "50% { transform: translate(2%, -1%) scale(1.18); } "
        "100% { transform: translate(4%, 1%) scale(1.13); }",
        "ease-in-out infinite alternate",
    ),
    "dolly_in": (
        "from { transform: scale(1.04); } to { transform: scale(1.24); }",
        "cubic-bezier(.17,.67,.33,1) infinite alternate",
    ),
    "subtle_breathing": (
        "0% { transform: scale(1.04); } 50% { transform: scale(1.09); } "
        "100% { transform: scale(1.05); }",
        "ease-in-out infinite",
    ),
}


def build_video_html(
    *,
    source_image_url: str,
    prompt: str,
    motion_preset: str,
    duration_seconds: int,
    mode: str = "image_to_video",
) -> str:
    keyframes, timing = _MOTION.get(motion_preset, _MOTION["slow_zoom"])
    # With no source (text_to_video) render an animated text stage instead.
    if source_image_url:
        stage = (
            f'<div class="stage"><img class="frame" '
            f'src="{html.escape(source_image_url)}" alt=""></div>'
        )
    else:
        stage = (
            '<div class="stage"><div class="frame textcard">'
            f"{html.escape(prompt)}</div></div>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<style>
  html, body {{ margin: 0; height: 100%; background: #0b0b0f; overflow: hidden;
    font-family: 'Segoe UI', Arial, sans-serif; }}
  .stage {{ position: absolute; inset: 0; display: flex; align-items: center;
    justify-content: center; }}
  .frame {{ max-width: 100%; max-height: 100%;
    animation: motion {duration_seconds}s {timing}; }}
  .textcard {{ max-width: 80%; padding: 8% 10%; text-align: center; color: #fff;
    font-size: 28px; line-height: 1.4; }}
  @keyframes motion {{ {keyframes} }}
  .badge {{ position: absolute; right: 16px; top: 14px; color: #fff;
    background: rgba(124,58,237,.85); padding: 4px 10px; border-radius: 999px;
    font-size: 12px; }}
  .cap {{ position: absolute; left: 16px; bottom: 14px; right: 16px; color: #fff;
    opacity: .85; font-size: 14px; }}
</style></head>
<body>
  {stage}
  <div class="badge">mock video · {html.escape(mode)}</div>
  <div class="cap">{html.escape(prompt)} — {duration_seconds}s</div>
</body></html>
"""


class MockVideoGenerator(VideoGenerator):
    async def generate(
        self,
        *,
        video_id: str,
        source_image_url: str,
        prompt: str,
        motion_preset: str,
        duration_seconds: int,
        mode: str = "image_to_video",
        quality_preset: str | None = None,
    ) -> VideoResult:
        await asyncio.sleep(_SIMULATED_LATENCY_SECONDS)
        output_dir = STORAGE_DIR / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{video_id}.html"
        (output_dir / filename).write_text(
            build_video_html(
                source_image_url=source_image_url,
                prompt=prompt,
                motion_preset=motion_preset,
                duration_seconds=duration_seconds,
                mode=mode,
            ),
            encoding="utf-8",
        )
        return VideoResult(result_url=f"/storage/videos/{filename}")
