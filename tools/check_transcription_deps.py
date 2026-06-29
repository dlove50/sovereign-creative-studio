"""Check local Video to Text dependencies without modifying the system."""
from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _env_value(name: str) -> str:
    current = os.getenv(name, "").strip()
    if current:
        return current
    env_path = ROOT / "backend" / ".env"
    if not env_path.is_file():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def main() -> int:
    configured = _env_value("FFMPEG_PATH")
    ffmpeg_path = None
    if configured:
        configured_path = Path(configured)
        try:
            if configured_path.is_file():
                ffmpeg_path = configured
        except OSError:
            if configured_path.name.lower() == "ffmpeg.exe":
                ffmpeg_path = configured
        if ffmpeg_path is None and configured_path.name.lower() == "ffmpeg.exe":
            ffmpeg_path = configured
    if ffmpeg_path is None:
        ffmpeg_path = shutil.which("ffmpeg")
    faster = importlib.util.find_spec("faster_whisper") is not None

    print("Sovereign Creative Studio - Video to Text dependency check")
    print(f"ffmpeg available: {'yes' if ffmpeg_path else 'no'}")
    print(f"ffmpeg path: {ffmpeg_path or '(missing)'}")
    print(f"faster-whisper importable: {'yes' if faster else 'no'}")
    print("")
    if not ffmpeg_path:
        print("Install ffmpeg and ensure ffmpeg.exe is on PATH, or set FFMPEG_PATH in backend/.env.")
    if not faster:
        print("Install faster-whisper with: backend\\.venv\\Scripts\\python.exe -m pip install -r backend\\requirements.txt")
    return 0 if ffmpeg_path and faster else 1


if __name__ == "__main__":
    raise SystemExit(main())
