from fastapi import APIRouter

from app.core.constants import NOT_AUTHENTICATED
from app.core.dependencies import CurrentUserDep
from app.models import User
from app.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get current user profile",
    responses={401: {"description": NOT_AUTHENTICATED}},
)
async def get_current_user_profile(current_user: CurrentUserDep) -> User:
    return current_user
