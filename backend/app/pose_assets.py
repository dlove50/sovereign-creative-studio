"""Bundle the preset OpenPose skeletons into STORAGE_DIR at startup.

The skeletons are pre-rendered (ComfyUI venv has the drawing deps; the API venv
does not), shipped under app/pose_presets/, and copied into
STORAGE_DIR/pose_presets/ so the pose workflows can resolve /storage/ URLs for
any configured STORAGE_DIR.
"""
import shutil

from .config import BASE_DIR, STORAGE_DIR

_BUNDLED = BASE_DIR / "app" / "pose_presets"


def ensure_pose_presets() -> None:
    dest = STORAGE_DIR / "pose_presets"
    dest.mkdir(parents=True, exist_ok=True)
    for png in _BUNDLED.glob("*.png"):
        target = dest / png.name
        if not target.is_file():
            shutil.copyfile(png, target)
