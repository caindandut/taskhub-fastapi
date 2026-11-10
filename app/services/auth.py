from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.core.constants import (
    EMAIL_ALREADY_REGISTERED,
    INACTIVE_USER,
    INCORRECT_CURRENT_PASSWORD,
    INVALID_CREDENTIALS,
    INVALID_TOKEN,
)
from app.core.exceptions import AuthenticationException, ConflictException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
    verify_password_dummy,
)
from app.models import RefreshToken, User
from app.models.enums import UserRole
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.auth import ChangePasswordRequest, LoginRequest, TokenResponse
from app.schemas.user import UserCreate, UserUpdate


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        token_repository: RefreshTokenRepository,
        settings: Settings,
    ) -> None:
        self.user_repository = user_repository
        self.token_repository = token_repository
        self.settings = settings

    async def register(self, payload: UserCreate) -> User:
        if await self.user_repository.get_by_email(payload.email) is not None:
            raise ConflictException(EMAIL_ALREADY_REGISTERED)
        user = User(
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            role=UserRole.MEMBER,
            is_active=True,
        )
        return await self.user_repository.create(user)

    async def _issue_tokens(self, user_id: int) -> TokenResponse:
        secret = self.settings.jwt_secret_key.get_secret_value()
        algorithm = self.settings.jwt_algorithm
        access_token = create_access_token(
            subject=user_id,
            secret_key=secret,
            algorithm=algorithm,
            expires_delta=timedelta(minutes=self.settings.access_token_expire_minutes),
        )
        refresh_token = create_refresh_token(
            subject=user_id,
            secret_key=secret,
            algorithm=algorithm,
            expires_delta=timedelta(days=self.settings.refresh_token_expire_days),
        )
        token_hash = hash_token(refresh_token)
        expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            days=self.settings.refresh_token_expire_days
        )
        await self.token_repository.create(
            RefreshToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self.user_repository.get_by_email(payload.email)
        if user is None:
            verify_password_dummy(payload.password)
            raise AuthenticationException(INVALID_CREDENTIALS)
        if not verify_password(payload.password, user.hashed_password):
            raise AuthenticationException(INVALID_CREDENTIALS)
        if not user.is_active:
            raise AuthenticationException(INACTIVE_USER)
        return await self._issue_tokens(user.id)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        secret = self.settings.jwt_secret_key.get_secret_value()
        algorithm = self.settings.jwt_algorithm
        user_id = decode_refresh_token(
            token=refresh_token,
            secret_key=secret,
            algorithm=algorithm,
        )
        token_hash = hash_token(refresh_token)
        token_record = await self.token_repository.get_by_token_hash(token_hash)
        if token_record is None or token_record.revoked_at is not None:
            raise AuthenticationException(INVALID_TOKEN)
        now = datetime.now(UTC).replace(tzinfo=None)
        if token_record.expires_at <= now:
            raise AuthenticationException(INVALID_TOKEN)

        user = await self.user_repository.get(user_id)
        if user is None:
            raise AuthenticationException(INVALID_TOKEN)
        if not user.is_active:
            raise AuthenticationException(INACTIVE_USER)

        await self.token_repository.update(token_record, {"revoked_at": now})
        return await self._issue_tokens(user.id)

    async def logout(self, refresh_token: str) -> None:
        secret = self.settings.jwt_secret_key.get_secret_value()
        algorithm = self.settings.jwt_algorithm
        decode_refresh_token(
            token=refresh_token,
            secret_key=secret,
            algorithm=algorithm,
        )
        token_hash = hash_token(refresh_token)
        token_record = await self.token_repository.get_by_token_hash(token_hash)
        if token_record is None or token_record.revoked_at is not None:
            raise AuthenticationException(INVALID_TOKEN)
        now = datetime.now(UTC).replace(tzinfo=None)
        await self.token_repository.update(token_record, {"revoked_at": now})

    async def get_current_user(self, token: str) -> User:
        user_id = decode_access_token(
            token=token,
            secret_key=self.settings.jwt_secret_key.get_secret_value(),
            algorithm=self.settings.jwt_algorithm,
        )
        user = await self.user_repository.get(user_id)
        if user is None:
            raise AuthenticationException(INVALID_TOKEN)
        if not user.is_active:
            raise AuthenticationException(INACTIVE_USER)
        return user

    async def update_profile(self, user: User, payload: UserUpdate) -> User:
        values = payload.model_dump(exclude_unset=True)
        if not values:
            return user
        return await self.user_repository.update(user, values)

    async def change_password(self, user: User, payload: ChangePasswordRequest) -> None:
        if not verify_password(payload.current_password, user.hashed_password):
            raise AuthenticationException(INCORRECT_CURRENT_PASSWORD)
        new_hashed_password = hash_password(payload.new_password)
        await self.user_repository.update(
            user, {"hashed_password": new_hashed_password}
        )
        await self.token_repository.revoke_all_for_user(user.id)
