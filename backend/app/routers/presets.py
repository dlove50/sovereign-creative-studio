from fastapi import APIRouter, HTTPException

from ..presets import get_preset, list_presets
from ..schemas import PresetOut

router = APIRouter(prefix="/api/presets", tags=["presets"])


@router.get("", response_model=list[PresetOut])
def list_all_presets():
    return list_presets()


@router.get("/{preset_id}", response_model=PresetOut)
def read_preset(preset_id: str):
    preset = get_preset(preset_id)
    if preset is None:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset
