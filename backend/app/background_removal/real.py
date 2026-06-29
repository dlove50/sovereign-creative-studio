"""Future real background-removal adapter placeholder."""
from pathlib import Path

from .base import BackgroundRemovalAdapter, BackgroundRemovalResult


class RealBackgroundRemovalAdapter(BackgroundRemovalAdapter):
    def remove_background(
        self, *, asset_id: str, original_path: Path, output_path: Path
    ) -> BackgroundRemovalResult:
        raise NotImplementedError("Real background removal is not configured yet")
