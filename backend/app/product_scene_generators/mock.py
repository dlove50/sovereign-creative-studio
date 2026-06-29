"""Mock product-scene generator."""
import html
import textwrap

from ..config import STORAGE_DIR
from .base import ProductSceneGenerator, ProductSceneResult

_PRESET_COLORS = {
    "studio": ("#f8fafc", "#cbd5e1", "#111827"),
    "luxury": ("#111827", "#b0892f", "#f8fafc"),
    "outdoor": ("#d9f99d", "#0f766e", "#14332b"),
    "social ad": ("#fdf2f8", "#ec4899", "#18181b"),
}


class MockProductSceneGenerator(ProductSceneGenerator):
    async def generate(
        self,
        *,
        scene_id: str,
        prompt: str,
        preset: str,
        product_image_url: str,
        mask_image_url: str | None = None,
        seg_prompt: str | None = None,
    ) -> ProductSceneResult:
        bg, accent, text = _PRESET_COLORS.get(preset, _PRESET_COLORS["studio"])
        lines = textwrap.wrap(prompt.strip(), width=34)[:4] or ["Product scene"]
        text_nodes = "".join(
            f'<text x="70" y="{760 + i * 42}" font-size="30" '
            f'font-family="Segoe UI, Arial, sans-serif" fill="{text}" '
            f'font-weight="700">{html.escape(line)}</text>'
            for i, line in enumerate(lines)
        )
        filename = f"{scene_id}.svg"
        output_dir = STORAGE_DIR / "product-scenes"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / filename).write_text(
            f"""<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{bg}"/>
      <stop offset="100%" stop-color="{accent}"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="18" stdDeviation="22" flood-color="#000000" flood-opacity="0.28"/>
    </filter>
  </defs>
  <rect width="1024" height="1024" fill="url(#bg)"/>
  <circle cx="840" cy="190" r="120" fill="#ffffff" opacity="0.22"/>
  <rect x="132" y="170" width="760" height="520" rx="34" fill="#ffffff" opacity="0.55"/>
  <image href="{html.escape(product_image_url)}" x="252" y="210" width="520" height="440" preserveAspectRatio="xMidYMid meet" filter="url(#shadow)"/>
  <text x="70" y="86" font-size="28" font-family="Segoe UI, Arial, sans-serif" fill="{text}" opacity="0.72" font-weight="700">{html.escape(preset.upper())}</text>
  {text_nodes}
</svg>
""",
            encoding="utf-8",
        )
        return ProductSceneResult(result_url=f"/storage/product-scenes/{filename}")
