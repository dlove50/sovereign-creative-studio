from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import LibraryItemOut
from ..services.library import build_library_items

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("", response_model=list[LibraryItemOut])
def list_library(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Unified media library built from existing asset/job tables."""
    return build_library_items(db, user, project_id)
