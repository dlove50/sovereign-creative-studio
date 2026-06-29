from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..models import User
from ..schemas import UserOut

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/me", response_model=UserOut)
def read_me(user: User = Depends(get_current_user)) -> User:
    return user
