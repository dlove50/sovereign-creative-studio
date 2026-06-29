"""Background-removal adapter interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BackgroundRemovalResult:
    processed_path: Path


class BackgroundRemovalAdapter(ABC):
    @abstractmethod
    def remove_background(
        self, *, asset_id: str, original_path: Path, output_path: Path
    ) -> BackgroundRemovalResult:
        raise NotImplementedError
