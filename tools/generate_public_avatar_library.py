"""Generate the studio's public avatar library locally (fictional people, our own images).

Phase 1 makes one portrait per avatar, phase 2 and 3 make two extra looks per avatar with the Qwen
image editor. It calls the backend's local image generator directly (no credits are charged), so ComfyUI must be up
and the backend virtualenv must be used: backend/.venv/Scripts/python.exe tools/generate_public_avatar_library.py. The script is resumable: files that already exist are skipped, so it can be stopped and
restarted. It writes web-sized WEBP files for the app, full-size PNG copies for a Downloads folder,
and a manifest the app reads.

Usage:  python tools/generate_public_avatar_library.py [--limit N] [--phase 1|2|3] [--remote http://host:port]

--remote sends the rendering to another ComfyUI (for example the Linux R9700 through an SSH tunnel). Two copies of
the script may run at once on different phases: the manifest is merged from disk before every write.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_APP = ROOT / "frontend" / "public" / "sovereign-ui" / "public-avatars"
MANIFEST = ROOT / "frontend" / "src" / "lib" / "public-avatars.generated.json"
OUT_DOWNLOADS = Path.home() / "Downloads" / "Sovereign Avatar Library"
STORAGE = ROOT / "backend" / "storage"
KEEP = "Keep the same person: same face, hair, skin tone, age and expression. "

# (slug, name, category, description, base setting, look A (label, edit), look B (label, edit))
AVATARS = [
    # --- Professional -------------------------------------------------------------------------
    ("nadia", "Nadia", "Professional", "a woman in her 30s with a sleek dark bob and warm brown skin, charcoal blazer over a cream blouse", "bright modern office, soft window light",
     ("Studio", "Place her in a clean grey photo studio with soft key light, same outfit."), ("Boardroom", "Place her at a glass boardroom table, wearing a navy suit jacket.")),
    ("tomas", "Tomas", "Professional", "a man in his 40s with short grey-streaked hair and light stubble, navy suit and open-collar white shirt", "neutral studio backdrop, soft light",
     ("Office", "Place him in a bright open-plan office, same outfit."), ("Casual friday", "Put him in a light blue knit sweater, same office background.")),
    ("imani", "Imani", "Professional", "a woman in her late 20s with natural curly hair and deep brown skin, emerald green blazer", "light grey studio background",
     ("Lobby", "Place her in a modern company lobby with warm lighting, same outfit."), ("Presenter", "Put her in a white tailored blouse in front of a soft blue gradient backdrop.")),
    ("kenji", "Kenji", "Professional", "a Japanese man in his 50s with neat short hair and round glasses, dark grey suit with a pale tie", "tidy office with bookshelves",
     ("Studio", "Place him in a clean light studio, same outfit."), ("Lecture hall", "Place him at a lectern in a university lecture hall, same outfit.")),
    ("priya", "Priya", "Professional", "a woman in her 40s of South Asian heritage with long black hair, burgundy blazer and gold earrings", "elegant office, warm light",
     ("Studio", "Place her in a neutral grey studio, same outfit."), ("Conference", "Place her on a conference stage with soft lights behind, same outfit.")),
    ("marcus", "Marcus", "Professional", "a man in his 30s with a short fade and trimmed beard, slate blue suit and white shirt, no tie", "modern glass office",
     ("Studio", "Place him in a seamless white studio, same outfit."), ("Rooftop", "Place him on an office rooftop terrace at golden hour, same outfit.")),
    # --- Lifestyle ----------------------------------------------------------------------------
    ("sofia", "Sofia", "Lifestyle", "a woman in her late 20s with wavy auburn hair and freckles, oatmeal knit sweater", "sunlit living room with plants",
     ("Cafe", "Place her in a cosy cafe by a window, same sweater."), ("Garden", "Place her in a green garden, in a light denim jacket.")),
    ("jonas", "Jonas", "Lifestyle", "a man in his early 30s with tousled blond hair and a short beard, olive green henley", "bright kitchen, morning light",
     ("Outdoors", "Place him on a hiking trail with trees behind, in a grey fleece."), ("Workshop", "Place him in a tidy woodworking workshop, wearing a canvas apron.")),
    ("leila", "Leila", "Lifestyle", "a woman in her 30s of Middle Eastern heritage with long dark hair, soft cream cardigan", "warm home study with bookshelves",
     ("Balcony", "Place her on a sunny balcony with city views, same cardigan."), ("Kitchen", "Place her in a bright kitchen, wearing a striped linen shirt.")),
    ("hiro", "Hiro", "Lifestyle", "a Japanese man in his late 20s with a relaxed side-swept haircut, beige overshirt over a white tee", "airy apartment, soft daylight",
     ("Street", "Place him on a quiet city street with warm evening light, same outfit."), ("Studio", "Place him in a minimalist art studio, wearing a black tee.")),
    ("camila", "Camila", "Lifestyle", "a woman in her 30s of Latina heritage with long wavy brown hair, yellow sundress", "sunny terrace with flowers",
     ("Market", "Place her at a bright outdoor market, same dress."), ("Home", "Place her in a cosy living room, in a soft green sweater.")),
    ("owen", "Owen", "Lifestyle", "a man in his 50s with a salt-and-pepper beard and kind eyes, flannel shirt", "rustic kitchen, warm light",
     ("Porch", "Place him on a wooden porch at sunset, same shirt."), ("Garage", "Place him in a neat garage workshop, wearing a denim work shirt.")),
    # --- UGC (creator style) -------------------------------------------------------------------
    ("zara", "Zara", "UGC", "a woman in her early 20s with a high ponytail and bright smile, pastel hoodie", "bedroom with fairy lights, ring-light glow",
     ("Car", "Place her in the driver's seat of a parked car, daylight through the window."), ("Cafe", "Place her at a trendy cafe table with a latte.")),
    ("dmitri", "Dmitri", "UGC", "a man in his mid 20s with messy dark hair and a light stubble, black tee and a thin chain", "gaming desk with soft RGB light",
     ("Gym", "Place him in a bright gym, wearing a grey tank top."), ("Street", "Place him on a city street, in a bomber jacket.")),
    ("yara", "Yara", "UGC", "a woman in her mid 20s with box braids and a warm smile, cropped denim jacket over a white top", "colourful apartment, daylight",
     ("Kitchen", "Place her in a bright kitchen, wearing an apron."), ("Outdoor", "Place her in a sunny park, same jacket.")),
    ("felix", "Felix", "UGC", "a man in his late 20s with curly brown hair and round glasses, mustard sweatshirt", "cosy home office with shelves",
     ("Cafe", "Place him in a busy cafe, same sweatshirt."), ("Beach", "Place him on a bright beach, wearing a linen shirt.")),
    ("amara", "Amara", "UGC", "a woman in her early 30s with a short natural afro and bold earrings, bright orange blouse", "modern living room, daylight",
     ("Studio", "Place her in a colourful photo studio backdrop, same blouse."), ("Market", "Place her at a farmers market, in a denim shirt.")),
    ("luca", "Luca", "UGC", "a man in his early 30s with slicked-back dark hair and a neat moustache, teal polo shirt", "bright balcony with plants",
     ("Kitchen", "Place him in a stylish kitchen, wearing a white chef's shirt."), ("Car", "Place him in a parked car with daylight through the window.")),
    # --- Community ----------------------------------------------------------------------------
    ("mei", "Mei", "Community", "a woman in her 60s of East Asian heritage with short silver hair and warm eyes, soft green blouse", "community centre, friendly light",
     ("Library", "Place her in a public library among shelves, same blouse."), ("Garden", "Place her in a community garden, wearing a straw hat.")),
    ("andre", "Andre", "Community", "a man in his 40s with a shaved head and a friendly smile, grey polo shirt with a name badge", "bright clinic reception",
     ("Clinic", "Put him in teal medical scrubs in a clean clinic corridor."), ("Outdoor", "Place him at a neighbourhood event outdoors, same polo shirt.")),
    ("greta", "Greta", "Community", "a woman in her 50s with a grey bob and reading glasses, cardigan over a blouse", "classroom with a whiteboard",
     ("Library", "Place her in a school library, same outfit."), ("Office", "Place her at a community office desk, wearing a navy blazer.")),
    ("samir", "Samir", "Community", "a man in his 30s of Arab heritage with short dark hair and a trimmed beard, hi-vis vest over a work shirt", "construction site, daylight",
     ("Workshop", "Place him in a clean workshop, wearing work overalls."), ("Office", "Place him in a site office, wearing a white shirt.")),
    ("noor", "Noor", "Community", "a woman in her 30s wearing a patterned headscarf and a smart blazer, warm smile", "bright community hall",
     ("Studio", "Place her in a neutral studio, same outfit."), ("Clinic", "Put her in white medical scrubs and a stethoscope in a clinic.")),
    ("theo", "Theo", "Community", "a man in his 70s with white hair and a kind lined face, cardigan and shirt", "cosy home, warm lamp light",
     ("Park", "Place him on a park bench with autumn trees, same cardigan."), ("Study", "Place him in a book-lined study, wearing a tweed jacket.")),
]


REMOTE: str | None = None


def make(prompt: str, source: str | None = None) -> str:
    """Run the local image generator directly (no credits, no database rows). Returns a /storage URL."""
    import asyncio
    import uuid

    sys.path.insert(0, str(ROOT / "backend"))
    from app.generators import get_generator  # noqa: E402 - needs the backend on sys.path

    generation_id = uuid.uuid4().hex
    generator = get_generator("local_comfyui", quality_preset=None if source else "krea2_turbo_fp8")
    if REMOTE:
        generator.base_url = REMOTE.rstrip("/")
    result = asyncio.run(generator.generate(
        generation_id=generation_id, prompt=prompt, media_type="image",
        mode="image_edit" if source else "text_to_image", source_image_url=source,
    ))
    return result.file_url


def save(file_url: str, slug: str, category: str, suffix: str = "") -> str:
    """Web WEBP into the app, PNG copy into Downloads. Returns the app-relative cover path."""
    src = STORAGE / Path(file_url).name
    name = f"{slug}{suffix}"
    OUT_APP.mkdir(parents=True, exist_ok=True)
    (OUT_DOWNLOADS / category).mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", "scale=-2:960", "-q:v", "82", str(OUT_APP / f"{name}.webp")], check=True)
    (OUT_DOWNLOADS / category / f"{name}.png").write_bytes(src.read_bytes())
    return f"/sovereign-ui/public-avatars/{name}.webp"


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {}


def write_manifest(state: dict) -> None:
    """Merge with what another copy of the script wrote, then replace the file atomically."""
    on_disk = load_manifest()
    for slug, entry in state.items():
        other = on_disk.setdefault(slug, entry)
        other["cover"] = other.get("cover") or entry.get("cover")
        other["source"] = other.get("source") or entry.get("source")
        known = {look["label"] for look in other["looks"]}
        other["looks"] += [look for look in entry["looks"] if look["label"] not in known]
        entry["looks"] = other["looks"]
        entry["cover"], entry["source"] = other["cover"], other["source"]
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(on_disk, indent=2), encoding="utf-8")
    tmp.replace(MANIFEST)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="only the first N avatars")
    parser.add_argument("--remote", default=None, help="ComfyUI base URL to render on instead of the local one")
    parser.add_argument("--phase", type=int, choices=(1, 2, 3), default=0, help="run one phase only")
    args = parser.parse_args()
    global REMOTE
    REMOTE = args.remote
    rows = AVATARS[: args.limit] if args.limit else AVATARS
    phases = [args.phase] if args.phase else [1, 2, 3]
    for phase in phases:
        state = load_manifest()  # re-read so another copy's progress is seen
        for slug, name, category, desc, setting, look_a, look_b in rows:
            entry = state.setdefault(slug, {"id": slug, "name": name, "category": category, "cover": None, "source": None, "looks": []})
            try:
                if phase == 1 and not entry["cover"]:
                    url = make(f"Waist-up portrait photo of {desc}, facing the camera, mouth closed, natural relaxed expression, {setting}, sharp focus, photorealistic")
                    entry["source"] = url
                    entry["cover"] = save(url, slug, category)
                elif phase in (2, 3) and entry["source"]:
                    label, edit = look_a if phase == 2 else look_b
                    if not any(l["label"] == label for l in entry["looks"]):
                        url = make(KEEP + edit, source=entry["source"])
                        entry["looks"].append({"label": label, "cover": save(url, slug, category, "-" + label.lower().replace(" ", "-"))})
                else:
                    continue
            except Exception as exc:  # noqa: BLE001 - keep going; the run is resumable
                print(f"[phase {phase}] {slug}: {exc}", file=sys.stderr)
                continue
            write_manifest(state)
            print(f"[phase {phase}] {slug} ok", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
