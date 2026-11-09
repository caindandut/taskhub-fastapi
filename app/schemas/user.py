from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PositiveInt,
    StringConstraints,
    field_validator,
)

from app.core.constants import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    USER_EMAIL_MAX_LENGTH,
    USER_NAME_MAX_LENGTH,
    USER_NAME_MIN_LENGTH,
)
from app.models.enums import UserRole

NormalizedEmail = Annotated[
    EmailStr,
    Field(max_length=USER_EMAIL_MAX_LENGTH),
]
UserFullName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=USER_NAME_MIN_LENGTH,
        max_length=USER_NAME_MAX_LENGTH,
    ),
]


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: NormalizedEmail
    full_name: UserFullName
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("password")
    @classmethod
    def reject_blank_password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Password cannot be blank")
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PositiveInt
    email: EmailStr
    full_name: UserFullName
    role: UserRole
    is_active: bool
    created_at: datetime
