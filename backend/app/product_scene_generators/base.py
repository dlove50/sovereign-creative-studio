"""Product ad scene generator interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProductSceneResult:
    result_url: str


class ProductSceneGenerator(ABC):
    @abstractmethod
    async def generate(
        self,
        *,
        scene_id: str,
        prompt: str,
        preset: str,
        product_image_url: str,
        mask_image_url: str | None = None,
        seg_prompt: str | None = None,
    ) -> ProductSceneResult:
        raise NotImplementedError
