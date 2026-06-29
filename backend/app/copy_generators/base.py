"""Copy generator interface. The mock implements this today; a real local LLM
or API backend slots in behind the same contract later."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CopyResult:
    result_text: str


class CopyGenerator(ABC):
    @abstractmethod
    async def generate(
        self,
        *,
        copy_id: str,
        copy_type: str,
        tone: str,
        audience: str | None,
        prompt: str,
        product_context: str | None = None,
    ) -> CopyResult:
        raise NotImplementedError
