"""Copy explicitly selected owned video exports into an owner's Sovereign project.

Imports finished videos, not editable provider timelines. Originals are untouched.
Usage: python tools/import_owned_videos.py --owner USER_ID FILE [FILE ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import config
from app.database import SessionLocal
from app.models import Project, User, VideoGeneration


def import_videos(paths: list[Path], owner: str) -> dict:
    project_id = uuid.uuid5(uuid.NAMESPACE_URL, f"sovereign:owned-video-imports:{owner}").hex
    imported, existing = [], []
    with SessionLocal() as db:
        user = db.get(User, owner)
        if user is None or user.role != "owner_admin":
            raise ValueError("Select the existing owner administrator.")
        project = db.get(Project, project_id)
        if not project:
            db.add(Project(id=project_id, user_id=owner, name="Imported HeyGen creations",
                           description="Finished video exports imported from Downloads. Original files retained."))
            db.flush()
        for path in paths:
            if path.suffix.lower() not in {".mp4", ".mov", ".webm"}:
                raise ValueError(f"Unsupported video: {path.name}")
            probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]))
            if not any(s.get("codec_type") == "video" and s.get("width", 0) > 0 for s in probe["streams"]):
                raise ValueError(f"No decodable video stream: {path.name}")
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            video_id = uuid.uuid5(uuid.NAMESPACE_URL, f"sovereign:owned-video:{owner}:{digest}").hex
            if db.get(VideoGeneration, video_id):
                existing.append(path.name)
                continue
            folder = config.STORAGE_DIR / "imports" / video_id
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / ("video" + path.suffix.lower())
            shutil.copy2(path, target)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(target), "-frames:v", "1", "-vf", "scale=640:-2", str(folder / "poster.jpg")], check=True)
            url = f"/storage/imports/{video_id}"
            db.add(VideoGeneration(id=video_id, user_id=owner, project_id=project_id,
                source_image_url=url + "/poster.jpg", mode="video_to_video", provider="imported",
                prompt=path.stem, motion_preset="imported", duration_seconds=math.ceil(float(probe["format"]["duration"])),
                credits_cost=0, status="completed", result_url=url + "/" + target.name,
                file_size_bytes=path.stat().st_size, completed_at=datetime.now(timezone.utc)))
            db.flush()  # Make same-batch duplicate hashes visible with autoflush disabled.
            (folder / "provenance.json").write_text(json.dumps({"original_filename": path.name,
                "sha256": digest, "source": "Owner-selected local video export", "editable_provider_timeline": False}, indent=2), encoding="utf-8")
            imported.append(path.name)
        db.commit()
    return {"project_id": project_id, "imported": imported, "already_present": existing}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps(import_videos(args.files, args.owner), indent=2))
