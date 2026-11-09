from datetime import timedelta

from app.core.config import Settings
from app.core.constants import (
    EMAIL_ALREADY_REGISTERED,
    INACTIVE_USER,
    INVALID_CREDENTIALS,
    INVALID_TOKEN,
)
from app.core.exceptions import AuthenticationException, ConflictException
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
    verify_password_dummy,
)
from app.models import User
from app.models.enums import UserRole
from app.repositories.user import UserRepository
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserCreate


class AuthService:
    def __init__(self, repository: UserRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    async def register(self, payload: UserCreate) -> User:
        if await self.repository.get_by_email(payload.email) is not None:
            raise ConflictException(EMAIL_ALREADY_REGISTERED)
        user = User(
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            role=UserRole.MEMBER,
            is_active=True,
        )
        return await self.repository.create(user)

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self.repository.get_by_email(payload.email)
        if user is None:
            verify_password_dummy(payload.password)
            raise AuthenticationException(INVALID_CREDENTIALS)
        if not verify_password(payload.password, user.hashed_password):
            raise AuthenticationException(INVALID_CREDENTIALS)
        if not user.is_active:
            raise AuthenticationException(INACTIVE_USER)
        access_token = create_access_token(
            subject=user.id,
            secret_key=self.settings.jwt_secret_key.get_secret_value(),
            algorithm=self.settings.jwt_algorithm,
            expires_delta=timedelta(minutes=self.settings.access_token_expire_minutes),
        )
        return TokenResponse(access_token=access_token)

    async def get_current_user(self, token: str) -> User:
        user_id = decode_access_token(
            token=token,
            secret_key=self.settings.jwt_secret_key.get_secret_value(),
            algorithm=self.settings.jwt_algorithm,
        )
        user = await self.repository.get(user_id)
        if user is None:
            raise AuthenticationException(INVALID_TOKEN)
        if not user.is_active:
            raise AuthenticationException(INACTIVE_USER)
        return user
