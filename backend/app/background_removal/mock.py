"""Mock background remover.

For now this copies the uploaded product image to the processed location. The
adapter shape matches a future real remover without pulling in image libraries.
"""
import shutil
from pathlib import Path

from .base import BackgroundRemovalAdapter, BackgroundRemovalResult


class MockBackgroundRemovalAdapter(BackgroundRemovalAdapter):
    def remove_background(
        self, *, asset_id: str, original_path: Path, output_path: Path
    ) -> BackgroundRemovalResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original_path, output_path)
        return BackgroundRemovalResult(processed_path=output_path)
