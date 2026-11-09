from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.constants import (
    EMAIL_ALREADY_REGISTERED,
    INVALID_CREDENTIALS,
    NOT_AUTHENTICATED,
)
from app.core.dependencies import CurrentUserDep, get_auth_service
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserCreate, UserRead
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    responses={409: {"description": EMAIL_ALREADY_REGISTERED}},
)
async def register(payload: UserCreate, service: AuthServiceDep) -> User:
    return await service.register(payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate user and return JWT access token",
    responses={401: {"description": INVALID_CREDENTIALS}},
)
async def login(payload: LoginRequest, service: AuthServiceDep) -> TokenResponse:
    return await service.login(payload)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get current authenticated user",
    responses={401: {"description": NOT_AUTHENTICATED}},
)
async def get_authenticated_user(current_user: CurrentUserDep) -> User:
    return current_user
