from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_authenticated_user
from ..services.local_media_library import local_media_items, resolve_media
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
    items = build_library_items(db, user, project_id)
    if not project_id:
        items.extend(local_media_items(user))
    return sorted(items, key=lambda item: item.created_at, reverse=True)


@router.get("/local-files/{relative:path}")
def local_file(relative: str, user: User = Depends(get_authenticated_user)):
    if user.role != "owner_admin":
        raise HTTPException(status_code=403, detail="Owner access required")
    try:
        path = resolve_media(relative)
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(path)
