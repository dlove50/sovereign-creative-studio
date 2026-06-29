"""Video generator interface. The mock implements this today; a real
ComfyUI/LTX/Wan/Hunyuan backend slots in behind the same contract later."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VideoResult:
    result_url: str
    provider_task_id: str | None = None


class VideoGenerator(ABC):
    @abstractmethod
    async def generate(
        self,
        *,
        video_id: str,
        source_image_url: str,
        prompt: str,
        motion_preset: str,
        duration_seconds: int,
        mode: str = "image_to_video",
        quality_preset: str | None = None,
    ) -> VideoResult:
        raise NotImplementedError
