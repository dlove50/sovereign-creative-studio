"""Video generator factory. Anything other than a known real backend falls back
to the mock, so the app keeps working without a video model configured."""
from ..config import (
    COMFYUI_BASE_URL,
    COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH,
    COMFYUI_VIDEO_ENGINE,
    COMFYUI_VIDEO_EXTENSION_WORKFLOW_PATH,
    COMFYUI_VIDEO_MODEL_NAME,
    COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH,
    COMFYUI_VIDEO_UPSCALE_MODEL_NAME,
    COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH,
    COMFYUI_VIDEO_WORKFLOW_PATH,
    COMFYUI_WAN_VIDEO_MODEL_NAME,
    COMFYUI_WAN_VIDEO_WORKFLOW_PATH,
    VIDEO_BACKEND,
)
from .base import VideoGenerator, VideoResult
from .comfyui import ComfyUIVideoGenerator
from .mock import MockVideoGenerator
from .seedance import SeedanceVideoGenerator

__all__ = [
    "ComfyUIVideoGenerator",
    "MockVideoGenerator",
    "SeedanceVideoGenerator",
    "VideoGenerator",
    "VideoResult",
    "get_video_generator",
]


def get_video_generator(provider: str = "local_ltx") -> VideoGenerator:
    if provider == "seedance_api":
        return SeedanceVideoGenerator()
    if VIDEO_BACKEND == "comfyui":
        workflow_path = COMFYUI_VIDEO_WORKFLOW_PATH
        model_name = COMFYUI_VIDEO_MODEL_NAME
        if COMFYUI_VIDEO_ENGINE == "wan":
            workflow_path = COMFYUI_WAN_VIDEO_WORKFLOW_PATH
            model_name = COMFYUI_WAN_VIDEO_MODEL_NAME
        return ComfyUIVideoGenerator(
            COMFYUI_BASE_URL,
            workflow_path,
            model_name,
            text_to_video_workflow_path=COMFYUI_TEXT_TO_VIDEO_WORKFLOW_PATH,
            video_upscale_workflow_path=COMFYUI_VIDEO_UPSCALE_WORKFLOW_PATH,
            upscale_model_name=COMFYUI_VIDEO_UPSCALE_MODEL_NAME,
            video_to_video_workflow_path=COMFYUI_VIDEO_TO_VIDEO_WORKFLOW_PATH,
            video_extension_workflow_path=COMFYUI_VIDEO_EXTENSION_WORKFLOW_PATH,
        )
    return MockVideoGenerator()
