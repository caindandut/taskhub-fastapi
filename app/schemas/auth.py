from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import PASSWORD_MAX_LENGTH
from app.schemas.user import NormalizedEmail


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
