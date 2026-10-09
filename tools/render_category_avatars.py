"""Resumable, single-flight Linux avatar category rendering. No cloud credits.

Saves the Comfy prompt ID before polling, so a slow model never triggers a duplicate
submission. Run with --remote http://127.0.0.1:18001. Stop/restart to resume.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.generators.comfyui import ComfyUIGenerator
from app.services.image_presets import workflow_for_preset

STATE = ROOT / "work" / "category-avatar-render.json"
PUBLIC = ROOT / "frontend" / "public" / "sovereign-ui" / "category-avatars"
EXPORT = Path.home() / "Downloads" / "Sovereign Avatar Library"
CATEGORIES = {
    "Office": (["sunlit glass office", "warm executive study", "modern boardroom", "creative coworking loft", "quiet office with bookshelves"], ["navy blazer and white shirt", "grey knit sweater", "cream tailored jacket", "smart blue button-down shirt"]),
    "Presentation": (["conference stage", "university lecture room", "webinar desk", "training studio", "presentation lounge"], ["navy suit", "beige blazer", "dark turtleneck", "smart casual shirt"]),
    "Studio": (["podcast studio", "white photography studio", "warm recording booth", "teal-lit creator desk", "minimal slate studio"], ["grey hoodie", "black crew-neck sweater", "olive overshirt", "cream knit polo"]),
    "Fitness": (["bright fitness studio", "yoga studio", "outdoor training park", "modern gym", "home workout room"], ["athletic zip jacket", "plain training tee", "modest sports top", "light running jacket"]),
    "Automotive": (["car showroom", "tidy repair workshop", "electric car display", "detailing bay", "dealership reception"], ["navy mechanic uniform", "smart polo shirt", "grey work jacket", "business casual blazer"]),
    "Construction": (["building site office", "new housing development", "industrial warehouse", "bridge construction site", "architectural model room"], ["yellow safety vest and hard hat", "orange safety vest and hard hat", "blue work jacket and hard hat", "white engineer shirt and hard hat"]),
    "Real Estate": (["modern home entrance", "bright apartment living room", "luxury kitchen", "new development showroom", "sunlit property terrace"], ["navy blazer", "cream suit jacket", "smart blue shirt", "charcoal business suit"]),
    "Medical": (["bright clinic", "hospital consultation room", "medical reception", "modern laboratory", "rehabilitation centre"], ["white medical coat", "teal scrubs", "blue scrubs", "white clinician jacket"]),
    "Home": (["sunlit living room", "warm kitchen", "home study", "cozy reading corner", "covered garden patio"], ["cream cardigan", "soft grey sweater", "linen shirt", "relaxed denim shirt"]),
}
PEOPLE = [
    "Black woman in her thirties with natural curls", "white man in his forties with short brown hair",
    "South Asian woman in her thirties with long dark hair", "East Asian man in his thirties with short hair",
    "Latina woman in her forties with wavy brown hair", "Black man in his thirties with a close beard",
    "white woman in her fifties with a blonde bob", "Middle Eastern man in his forties with dark hair",
    "East Asian woman in her fifties with short hair", "Latino man in his thirties with curly hair",
    "Black woman in her fifties with short silver hair", "South Asian man in his forties with glasses",
    "white woman in her thirties with auburn curls", "Black man in his fifties with salt-and-pepper hair",
    "Middle Eastern woman in her thirties wearing a neat headscarf", "white man in his sixties with grey hair",
    "East Asian woman in her twenties with a dark bob", "South Asian man in his thirties with a beard",
    "Latina woman in her fifties with shoulder-length hair", "East Asian man in his fifties with glasses",
]


def catalog():
    rows = []
    for category, (settings, outfits) in CATEGORIES.items():
        for i, person in enumerate(PEOPLE):
            outfit, setting = outfits[i % 4], settings[i // 4]
            slug = category.lower().replace(" ", "-") + f"-{i + 1:02}"
            edit = f"Dress them in a {outfit}, in a {setting}."
            rows.append({"id": slug, "name": f"{category} {i + 1:02}", "category": category,
                "description": f"{outfit.capitalize()} · {setting}", "cover": None, "looks": [],
                "prompt": f"Photorealistic waist-up portrait of a fictional {person}, wearing a {outfit}, in a {setting}. Facing camera, natural relaxed expression, clear unobstructed face, hands relaxed, realistic anatomy, professional soft lighting. One person, no text, no logos.",
                "edit_prompt": edit})
    return rows


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(path)


def publish(state):
    write_json(PUBLIC / "catalog.json", {"target": 180, "avatars": list(state.values())})


def run(remote, limit):
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    generator = ComfyUIGenerator(remote, str(workflow_for_preset("krea2_turbo_fp8")))
    rows = catalog()[:limit] if limit else catalog()
    PUBLIC.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=remote, timeout=60) as client:
        for row in rows:
            entry = state.setdefault(row["id"], row)
            if entry.get("cover"):
                continue
            if entry.get("status") in {"failed", "submission-unknown"}:
                print(f"Needs review: {row['id']}", flush=True)
                continue
            if not entry.get("prompt_id"):
                while True:
                    response = client.get("/queue"); response.raise_for_status()
                    queue = response.json()
                    if not queue["queue_running"] and not queue["queue_pending"]:
                        break
                    time.sleep(10)
                entry["status"] = "submission-unknown"
                write_json(STATE, state)
                response = client.post("/prompt", json={"prompt": generator._build_workflow(entry["prompt"])})
                response.raise_for_status()
                entry["prompt_id"] = response.json()["prompt_id"]
                entry["status"] = "rendering"
                write_json(STATE, state); publish(state)
                print(f"Submitted {row['id']} {entry['prompt_id']}", flush=True)
            started = time.monotonic()
            while True:
                response = client.get(f"/history/{entry['prompt_id']}"); response.raise_for_status()
                history = response.json().get(entry["prompt_id"])
                if history and history.get("status", {}).get("completed"):
                    image = generator._first_image(history["outputs"])
                    result = client.get("/view", params={k: image.get(k, "output" if k == "type" else "") for k in ("filename", "subfolder", "type")})
                    result.raise_for_status()
                    dest = EXPORT / entry["category"] / (entry["id"] + ".png")
                    dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(result.content)
                    target = PUBLIC / (entry["id"] + ".webp")
                    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(dest), "-vf", "scale=-2:960", "-q:v", "82", str(target)], check=True)
                    entry["cover"] = "/sovereign-ui/category-avatars/" + target.name
                    entry["status"] = "completed"
                    write_json(STATE, state); publish(state)
                    print(f"Completed {entry['id']}", flush=True)
                    break
                if history and history.get("status", {}).get("status_str") == "error":
                    entry["status"] = "failed"; write_json(STATE, state); publish(state)
                    raise RuntimeError(f"Render failed: {entry['prompt_id']}; inspect Comfy history")
                if time.monotonic() - started > 7200:
                    raise TimeoutError(f"Still pending {entry['prompt_id']}; restart to resume without resubmission")
                time.sleep(10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    run(args.remote.rstrip("/"), args.limit)
