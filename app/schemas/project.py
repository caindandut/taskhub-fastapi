from __future__ import annotations

from typing import Annotated

from pydantic import ConfigDict, Field, field_validator

from app.core.constants import (
    PROJECT_DESCRIPTION_MAX_LENGTH,
    PROJECT_NAME_CANNOT_BE_BLANK,
    PROJECT_NAME_MAX_LENGTH,
    PROJECT_NAME_MIN_LENGTH,
)
from app.models.enums import ProjectStatus
from app.schemas.base import BaseSchema, UtcDatetime, require_not_null


def _validate_project_name(value: str) -> str:
    if not value:
        raise ValueError(PROJECT_NAME_CANNOT_BE_BLANK)
    return value


def _normalize_project_description(value: str | None) -> str | None:
    if value is None:
        return None
    return value or None


class ProjectCreate(BaseSchema):
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
        return _validate_project_name(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return _normalize_project_description(value)


class ProjectUpdate(BaseSchema):
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
        return _validate_project_name(require_not_null(value))

    @field_validator("status")
    @classmethod
    def reject_null_status(cls, value: ProjectStatus | None) -> ProjectStatus:
        return require_not_null(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return _normalize_project_description(value)


class ProjectRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    name: str
    description: str | None
    status: ProjectStatus
    created_at: UtcDatetime
