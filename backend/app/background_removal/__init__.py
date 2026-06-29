"""Background-removal adapter factory."""
from .base import BackgroundRemovalAdapter, BackgroundRemovalResult
from .mock import MockBackgroundRemovalAdapter

__all__ = [
    "BackgroundRemovalAdapter",
    "BackgroundRemovalResult",
    "MockBackgroundRemovalAdapter",
    "get_background_removal_adapter",
]


def get_background_removal_adapter() -> BackgroundRemovalAdapter:
    return MockBackgroundRemovalAdapter()
