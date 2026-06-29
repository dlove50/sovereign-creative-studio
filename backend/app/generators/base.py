"""Generator interface. Every backend (mock today, ComfyUI later) implements
this, so the API layer never changes when the engine is swapped."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class GenerationResult:
    file_url: str  # public URL path, e.g. "/storage/<id>.svg"


class Generator(ABC):
    @abstractmethod
    async def generate(
        self,
        *,
        generation_id: str,
        prompt: str,
        media_type: str,
        mode: str = "text_to_image",
        source_image_url: str | None = None,
    ) -> GenerationResult:
        """Produce an asset for the prompt and return its public URL.

        Implementations must write the asset under config.STORAGE_DIR and
        return a URL path served by the /storage static mount."""
        raise NotImplementedError
