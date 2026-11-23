from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    PositiveInt,
    StringConstraints,
    field_validator,
)

from app.core.constants import (
    PASSWORD_CANNOT_BE_BLANK,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    USER_EMAIL_MAX_LENGTH,
    USER_NAME_MAX_LENGTH,
    USER_NAME_MIN_LENGTH,
)
from app.models.enums import UserRole
from app.schemas.base import BaseSchema, UtcDatetime, require_not_null


def _normalize_email(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _reject_blank_password(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        raise ValueError(PASSWORD_CANNOT_BE_BLANK)
    return value


NormalizedEmail = Annotated[
    EmailStr,
    BeforeValidator(_normalize_email),
    Field(max_length=USER_EMAIL_MAX_LENGTH),
]

RawPassword = Annotated[
    str,
    BeforeValidator(_reject_blank_password),
    Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH),
]

UserFullName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=USER_NAME_MIN_LENGTH,
        max_length=USER_NAME_MAX_LENGTH,
    ),
]


class UserCreate(BaseSchema):
    email: NormalizedEmail
    full_name: UserFullName
    password: RawPassword


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PositiveInt
    email: EmailStr
    full_name: UserFullName
    role: UserRole
    is_active: bool
    created_at: UtcDatetime


class UserUpdate(BaseSchema):
    full_name: UserFullName | None = None

    @field_validator("full_name")
    @classmethod
    def reject_explicit_null(cls, value: str | None) -> str:
        return require_not_null(value)
