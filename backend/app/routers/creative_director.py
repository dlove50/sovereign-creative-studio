from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import CreativeBrief, Project, User
from ..schemas import CreativeDirectorOut, CreativeDirectorRequest
from ..services.creative_director import build_recommendations

router = APIRouter(prefix="/api/creative-director", tags=["creative-director"])


@router.post("/recommendations", response_model=CreativeDirectorOut)
def recommendations(
    payload: CreativeDirectorRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = db.get(Project, payload.project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    brief = None
    if payload.brief_id:
        brief = db.get(CreativeBrief, payload.brief_id)
        if brief is None or brief.project_id != project.id:
            raise HTTPException(status_code=404, detail="Creative brief not found")

    return build_recommendations(db, project, brief)
