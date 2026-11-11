from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.constants import (
    EMAIL_ALREADY_REGISTERED,
    INVALID_CREDENTIALS,
    INVALID_TOKEN,
)
from app.core.dependencies import get_auth_service
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
)
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
    summary="Authenticate user and return JWT access and refresh tokens",
    responses={401: {"description": INVALID_CREDENTIALS}},
)
async def login(payload: LoginRequest, service: AuthServiceDep) -> TokenResponse:
    return await service.login(payload)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token using a valid refresh token",
    responses={401: {"description": INVALID_TOKEN}},
)
async def refresh(
    payload: RefreshTokenRequest, service: AuthServiceDep
) -> TokenResponse:
    return await service.refresh(payload.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke refresh token and log out",
    responses={401: {"description": INVALID_TOKEN}},
)
async def logout(payload: RefreshTokenRequest, service: AuthServiceDep) -> Response:
    await service.logout(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
