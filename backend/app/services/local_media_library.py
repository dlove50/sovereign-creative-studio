"""Read the organized owner media folder without exposing arbitrary local files."""
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from ..schemas import LibraryItemOut

MEDIA_ROOT = Path(os.environ.get("SOVEREIGN_MEDIA_ROOT", str(Path.home() / "Downloads" / "Sovereign")))
FOLDERS = {"Images", "Sound Bites", "Videos"}
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".mp4", ".mov", ".webm"}
AUDIO = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
VIDEO = {".mp4", ".mov", ".webm"}


def resolve_media(relative: str) -> Path:
    root = MEDIA_ROOT.resolve()
    path = (root / relative).resolve()
    rel = path.relative_to(root)
    if not rel.parts or rel.parts[0] not in FOLDERS or path.suffix.lower() not in EXTENSIONS or not path.is_file():
        raise ValueError("Not a library media file")
    return path


def local_media_items(user) -> list[LibraryItemOut]:
    if user.role != "owner_admin":
        return []
    items = []
    root = MEDIA_ROOT.resolve()
    for folder in sorted(FOLDERS):
        for candidate in (root / folder).rglob("*"):
            if candidate.suffix.lower() not in EXTENSIONS:
                continue
            relative = candidate.relative_to(root).as_posix()
            try:
                path = resolve_media(relative)
            except (ValueError, OSError):
                continue
            kind = "video" if path.suffix.lower() in VIDEO else "upload" if path.suffix.lower() in AUDIO else "image"
            url = "/api/library/local-files/" + quote(relative, safe="/")
            items.append(LibraryItemOut(
                id="local:" + relative, type=kind, title=path.stem,
                description="Sovereign / " + relative, status="completed",
                asset_url=url, download_url=url, thumbnail_url=url if kind == "image" else None,
                created_at=datetime.fromtimestamp(path.stat().st_mtime),
                source_entity_id=relative,
                source_entity_type="local_audio" if path.suffix.lower() in AUDIO else "local_media",
            ))
    return items
