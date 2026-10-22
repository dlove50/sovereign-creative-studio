"""Local export helpers: resolve /storage URLs to files and build campaign zips.

Lightweight and local — no cloud, no cleanup daemon. Zips are written under
EXPORT_DIR and streamed back to the client."""
import json
import zipfile
from pathlib import Path

from ..config import EXPORT_DIR, STORAGE_DIR

_STORAGE_URL_PREFIX = "/storage/"


def storage_path_for(file_url: str | None) -> Path | None:
    """Map a public /storage/... URL to its local file path, or None."""
    if not file_url or not file_url.startswith(_STORAGE_URL_PREFIX):
        return None
    relative = Path(file_url[len(_STORAGE_URL_PREFIX) :])
    # Reject traversal and absolute components, which would escape STORAGE_DIR
    # (an absolute right-hand side replaces the left when joined). Deliberately
    # not resolve()d: export folders can be junctions, and resolving them would
    # reject legitimate reads.
    if relative.is_absolute() or ".." in relative.parts:
        return None
    return STORAGE_DIR / relative


def build_campaign_zip(
    *,
    bundle_name: str,
    image_path: Path | None,
    image_arcname: str | None,
    copy_text: str | None,
    metadata: dict,
) -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = EXPORT_DIR / f"{bundle_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if image_path is not None and image_path.is_file():
            zf.write(image_path, arcname=image_arcname or image_path.name)
        if copy_text is not None:
            zf.writestr("copy.txt", copy_text)
        zf.writestr("metadata.json", json.dumps(metadata, indent=2, default=str))
    return zip_path
