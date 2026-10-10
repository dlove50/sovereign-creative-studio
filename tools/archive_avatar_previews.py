"""Verify newly completed previews and index immutable library copies."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    media = Path.home() / "Downloads/Sovereign"
    destination = media / "Videos/Avatar Previews"
    destination.mkdir(parents=True, exist_ok=True)
    manifest = media / "Manifests/avatar-previews.json"
    records = {r["presenter"]: r for r in json.loads(manifest.read_text())} if manifest.exists() else {}
    state = json.loads((ROOT / "work/hover-previews.json").read_text())
    added = 0
    for slug, row in state.items():
        if row.get("status") != "completed":
            continue
        source = ROOT / "frontend/public/sovereign-ui/public-avatars/previews" / (slug + ".mp4")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        target = destination / source.name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Archive differs; preserve both and inspect: {slug}")
        if records.get(slug, {}).get("sha256") == digest and target.exists():
            continue
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(source), "-f", "null", "-"], check=True)
        if not target.exists():
            shutil.copy2(source, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError(f"Archive verification failed: {slug}")
        records[slug] = dict(presenter=slug, file=str(target), sha256=digest,
                             bytes=target.stat().st_size, decode_verified=True, visual_review="pending")
        added += 1
    manifest.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest.with_suffix(".tmp")
    temporary.write_text(json.dumps(list(records.values()), indent=2))
    temporary.replace(manifest)
    print(f"Newly verified: {added}; archived previews: {len(records)}")


if __name__ == "__main__":
    main()
