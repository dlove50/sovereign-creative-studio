"""Generator factory. One place decides which backend is active.

Anything other than "comfyui" falls back to the mock generator, so a missing or
misconfigured backend never takes the app down."""
from ..config import COMFYUI_BASE_URL, GENERATOR_BACKEND
from ..services.image_presets import workflow_for_preset
from .base import GenerationResult, Generator
from .comfyui import ComfyUIGenerator
from .mock import MockGenerator
from .openai_image import OpenAIImageGenerator

__all__ = ["Generator", "GenerationResult", "OpenAIImageGenerator", "get_generator"]


def get_generator(provider: str = "local_comfyui", quality_preset: str | None = None) -> Generator:
    if provider == "openai_image_api":
        return OpenAIImageGenerator()
    if GENERATOR_BACKEND == "comfyui":
        # The chosen quality preset selects which local workflow (model) renders.
        return ComfyUIGenerator(COMFYUI_BASE_URL, str(workflow_for_preset(quality_preset)))
    return MockGenerator()
