"""Expand existing fictional presenters to 15 distinct looks on local ComfyUI.

Single worker, one request at a time. Stops on uncertain failure rather than
automatically submitting the same expensive edit again.
"""
import json
import argparse
import time
from pathlib import Path

import httpx
import generate_public_avatar_library as library

library.REMOTE = None
STATE = library.ROOT / "work" / "expanded-avatar-looks.json"
VARIANTS = [
    ("Podcast", "Wear a charcoal crewneck sweater at a podcast desk with warm lamps."),
    ("Executive", "Wear a navy tailored suit in a glass office overlooking the city."),
    ("Creative loft", "Wear a denim shirt in a bright creative loft with plants."),
    ("Presentation", "Wear a burgundy blazer on a conference stage with soft blue lights."),
    ("Home office", "Wear a cream cardigan in a sunlit home office."),
    ("Fitness", "Wear a modest athletic tracksuit in a clean fitness studio."),
    ("Automotive", "Wear navy mechanic coveralls in a bright automotive workshop."),
    ("Construction", "Wear a safety vest and hard hat at a building site."),
    ("Real estate", "Wear a light grey business suit in a modern house entrance."),
    ("Medical", "Wear teal medical scrubs in a bright clinic."),
    ("Kitchen", "Wear a white shirt and green apron in a modern kitchen."),
    ("Garden", "Wear a casual olive jacket in a garden at golden hour."),
    ("Library", "Wear a brown tweed blazer in a wood-panelled library."),
    ("Studio white", "Wear a black turtleneck against a white studio background."),
]


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=int, choices=[15], default=15)
    parser.add_argument('--remote', default=None)
    args = parser.parse_args()
    library.REMOTE = args.remote
    endpoint = args.remote or 'http://127.0.0.1:8001'
    variants = list(VARIANTS)
    if args.target == 50:
        for setting, scene in [('Atrium','a sunlit modern atrium'), ('Newsroom','a professional newsroom'), ('Gallery','a contemporary art gallery'), ('Terrace','a city rooftop terrace'), ('Workshop','a makers workshop'), ('Lounge','a warm hotel lounge'), ('Campus','a leafy university campus')]:
            for style, outfit in [('Formal','a tailored charcoal suit'), ('Linen','an ivory linen jacket'), ('Casual','a dark denim jacket'), ('Knit','a forest-green knitted sweater'), ('Creative','a rust-colored overshirt')]:
                variants.append((setting+' '+style, 'Wear '+outfit+' in '+scene+'. Medium portrait, natural light and confident relaxed pose.'))
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    manifest = library.load_manifest()
    for slug, entry in manifest.items():
        for label, prompt in variants:
            if len(entry["looks"]) >= args.target - 1:
                break
            if any(look["label"] == label for look in entry["looks"]):
                continue
            key = slug + ":" + label
            if state.get(key) == "submitted":
                raise RuntimeError(f"Unresolved render {key}; inspect Comfy history before resuming")
            while True:
                with httpx.Client(trust_env=False, timeout=15) as client:
                    response = client.get(endpoint + "/queue")
                    response.raise_for_status()
                    queue = response.json()
                if not queue["queue_running"] and not queue["queue_pending"]:
                    break
                time.sleep(10)
            state[key] = "submitted"
            STATE.write_text(json.dumps(state, indent=2))
            print("Rendering", key, flush=True)
            url = library.make(library.KEEP + prompt, source=entry["source"])
            cover = library.save(url, slug, entry["category"], "-suite-" + label.lower().replace(" ", "-"))
            entry["looks"].append({"label": label, "cover": cover})
            library.write_manifest(manifest)
            catalog = library.OUT_APP / "catalog.json"
            temporary = catalog.with_suffix(".tmp")
            temporary.write_text(json.dumps(manifest, indent=2))
            temporary.replace(catalog)
            state[key] = "completed"
            STATE.write_text(json.dumps(state, indent=2))
            print("Completed", key, flush=True)


if __name__ == "__main__":
    run()
