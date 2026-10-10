"""Make the original tile pictures for the Director templates with the local z-image model.

Needs the main ComfyUI (127.0.0.1:8001) to be up. Run with the backend venv:
    backend/.venv/Scripts/python.exe tools/generate_director_tiles.py [--only id,id] [--force]
Writes frontend/public/sovereign-ui/director/<id>.webp (skips files that exist unless --force).
Prompts avoid brand names, logos, readable text and real people on purpose.
"""
from __future__ import annotations

import argparse
import io
import json
import time
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "backend" / "workflows" / "text_to_image_z_image_turbo.json"
OUT = ROOT / "frontend" / "public" / "sovereign-ui" / "director"
COMFY = "http://127.0.0.1:8001"
WIDTH, HEIGHT = 832, 1024
STYLE = ", highly detailed, cinematic lighting, no text, no logos, no watermark"

TILES = {
    "short-film": "cinematic film still, a lone lighthouse keeper on a storm-lashed rocky coast at dusk, teal and amber light, anamorphic lens, film grain",
    "music-video": "a singer in silhouette on a neon-lit stage holding a vintage microphone, stage haze and rim light, magenta and cyan, concert photography",
    "real-estate": "modern two-storey house exterior at golden hour, glass and warm timber, landscaped garden and walkway, architectural photography",
    "product-ads": "studio product photograph of round amber tinted sunglasses on a glossy white pedestal, soft gradient backdrop, crisp reflections",
    "ad-remake": "two-panel collage, left a vintage 1990s style fashion advert photo, right a modern re-shoot of the same pose, playful pop colours",
    "social-content": "a young creator filming a skateboard trick in a sunny city plaza with a phone on a gimbal, vibrant street style, motion energy",
    "ugc-ads": "a friendly person holding up a small skincare jar towards a phone camera in a bright bedroom, ring light reflection, authentic casual feel",
    "micro-drama": "two people in a tense emotional moment by a rain-streaked apartment window at night, city lights bokeh, shallow depth of field, romance drama still",
    "brand-film": "hands shaping a ceramic mug on a pottery wheel, warm natural window light, artisan craft, documentary style",
    "explainer": "friendly cartoon characters gathered around a glowing lightbulb on a whiteboard, flat illustration, soft pastel palette",
    "film-trailer": "a lone explorer in a yellow raincoat walking toward a huge glowing doorway in a misty forest, epic movie poster composition",
    "promo-video": "floating abstract app interface cards over a soft pastel gradient, clean modern 3d render, depth and glow",
}


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(COMFY + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _get(path: str) -> bytes:
    with urllib.request.urlopen(COMFY + path, timeout=120) as resp:
        return resp.read()


def render(prompt: str, seed: int) -> Image.Image:
    graph = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    for node in graph.values():
        for key, value in node["inputs"].items():
            if value == "__PROMPT__":
                node["inputs"][key] = prompt + STYLE
    graph["7"]["inputs"].update(width=WIDTH, height=HEIGHT)
    graph["8"]["inputs"]["seed"] = seed
    prompt_id = _post("/prompt", {"prompt": graph})["prompt_id"]
    deadline = time.time() + 600
    while time.time() < deadline:
        history = json.loads(_get(f"/history/{prompt_id}"))
        entry = history.get(prompt_id)
        if entry:
            if entry.get("status", {}).get("status_str") != "success":
                raise RuntimeError(f"ComfyUI failed: {entry.get('status', {}).get('messages', [])[-1:]}")
            image = entry["outputs"]["10"]["images"][0]
            query = f"filename={image['filename']}&subfolder={image.get('subfolder', '')}&type={image.get('type', 'output')}"
            return Image.open(io.BytesIO(_get("/view?" + query))).convert("RGB")
        time.sleep(1.5)
    raise TimeoutError("ComfyUI took too long.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    wanted = [t for t in args.only.split(",") if t] or list(TILES)
    OUT.mkdir(parents=True, exist_ok=True)
    for tile_id in wanted:
        target = OUT / f"{tile_id}.webp"
        if target.exists() and not args.force:
            print(f"skip {tile_id} (exists)")
            continue
        started = time.time()
        render(TILES[tile_id], seed=abs(hash(tile_id)) % (2**31)).save(target, "WEBP", quality=88)
        print(f"ok   {tile_id} ({time.time() - started:.0f}s) -> {target.name}")


if __name__ == "__main__":
    main()
