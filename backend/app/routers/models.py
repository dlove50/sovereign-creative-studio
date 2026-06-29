from fastapi import APIRouter

from ..schemas import ModelCheckOut, ModelManagerStatusOut, WorkflowCheckOut
from ..services.model_manager import (
    build_model_manager_status,
    image_model_checks,
    video_model_checks,
    workflow_checks,
)

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/status", response_model=ModelManagerStatusOut)
def model_status():
    return build_model_manager_status()


@router.get("/image", response_model=list[ModelCheckOut])
def image_models():
    return image_model_checks()


@router.get("/video", response_model=list[ModelCheckOut])
def video_models():
    return video_model_checks()


@router.get("/workflows", response_model=list[WorkflowCheckOut])
def workflows():
    return workflow_checks()
