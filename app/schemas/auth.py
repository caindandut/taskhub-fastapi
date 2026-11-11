from pydantic import Field

from app.core.constants import PASSWORD_MAX_LENGTH
from app.schemas.base import BaseSchema
from app.schemas.user import NormalizedEmail, RawPassword


class LoginRequest(BaseSchema):
    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class RefreshTokenRequest(BaseSchema):
    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(BaseSchema):
    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: RawPassword


class TokenResponse(BaseSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
