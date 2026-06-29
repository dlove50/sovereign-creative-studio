from fastapi import APIRouter

from ..schemas import (
    WorkflowCheckOut,
    WorkflowConfigUpdate,
    WorkflowConfigUpdateResult,
    WorkflowManagerModelsOut,
    WorkflowManagerStatusOut,
)
from ..services import workflow_manager

router = APIRouter(prefix="/api/workflow-manager", tags=["workflow-manager"])


@router.get("/status", response_model=WorkflowManagerStatusOut)
def status():
    return workflow_manager.get_status()


@router.get("/models", response_model=WorkflowManagerModelsOut)
def models():
    return workflow_manager.get_models()


@router.get("/workflows", response_model=list[WorkflowCheckOut])
def workflows():
    return workflow_manager.get_workflows()


@router.put("/config", response_model=WorkflowConfigUpdateResult)
def update_config(payload: WorkflowConfigUpdate):
    return workflow_manager.update_config(payload.model_dump(exclude_unset=True))
