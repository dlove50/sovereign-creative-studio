"""Copy generator factory. Anything other than a known real backend falls back
to the mock, so the app keeps working without an LLM configured.

local-qwen / local-deepseek are Ollama presets that pin a specific local model.
"""
from ..config import (
    COPY_BACKEND,
    OLLAMA_DEEPSEEK_MODEL,
    OLLAMA_QWEN_MODEL,
)
from .base import CopyGenerator, CopyResult
from .claude import ClaudeCopyGenerator
from .gemini import GeminiCopyGenerator
from .mock import MockCopyGenerator
from .ollama import OllamaCopyGenerator
from .openai import OpenAICopyGenerator

__all__ = [
    "ClaudeCopyGenerator",
    "CopyGenerator",
    "CopyResult",
    "GeminiCopyGenerator",
    "MockCopyGenerator",
    "OllamaCopyGenerator",
    "OpenAICopyGenerator",
    "get_copy_generator",
]


def get_copy_generator() -> CopyGenerator:
    if COPY_BACKEND == "openai":
        return OpenAICopyGenerator()
    if COPY_BACKEND == "ollama":
        return OllamaCopyGenerator()
    if COPY_BACKEND == "local-qwen":
        return OllamaCopyGenerator(model=OLLAMA_QWEN_MODEL)
    if COPY_BACKEND == "local-deepseek":
        return OllamaCopyGenerator(model=OLLAMA_DEEPSEEK_MODEL)
    if COPY_BACKEND == "claude":
        return ClaudeCopyGenerator()
    if COPY_BACKEND == "gemini":
        return GeminiCopyGenerator()
    return MockCopyGenerator()
