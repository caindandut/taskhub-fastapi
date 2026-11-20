from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import (
    FIELD_CANNOT_BE_NULL,
    PROJECT_DESCRIPTION_MAX_LENGTH,
    PROJECT_NAME_CANNOT_BE_BLANK,
    PROJECT_NAME_MAX_LENGTH,
    PROJECT_NAME_MIN_LENGTH,
)
from app.models.enums import ProjectStatus


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str,
        Field(
            min_length=PROJECT_NAME_MIN_LENGTH,
            max_length=PROJECT_NAME_MAX_LENGTH,
        ),
    ]
    description: Annotated[
        str | None,
        Field(default=None, max_length=PROJECT_DESCRIPTION_MAX_LENGTH),
    ] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError(PROJECT_NAME_CANNOT_BE_BLANK)
        return trimmed

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed if trimmed else None


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[
        str | None,
        Field(
            default=None,
            min_length=PROJECT_NAME_MIN_LENGTH,
            max_length=PROJECT_NAME_MAX_LENGTH,
        ),
    ] = None
    description: Annotated[
        str | None,
        Field(default=None, max_length=PROJECT_DESCRIPTION_MAX_LENGTH),
    ] = None
    status: ProjectStatus | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError(FIELD_CANNOT_BE_NULL)
        trimmed = value.strip()
        if not trimmed:
            raise ValueError(PROJECT_NAME_CANNOT_BE_BLANK)
        return trimmed

    @field_validator("status")
    @classmethod
    def reject_null_status(cls, value: ProjectStatus | None) -> ProjectStatus:
        if value is None:
            raise ValueError(FIELD_CANNOT_BE_NULL)
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed if trimmed else None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    name: str
    description: str | None
    status: ProjectStatus
    created_at: datetime
