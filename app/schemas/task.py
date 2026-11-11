from typing import Annotated

from pydantic import ConfigDict, Field, field_validator

from app.core.constants import (
    TASK_DESCRIPTION_MAX_LENGTH,
    TASK_TITLE_MAX_LENGTH,
    TASK_TITLE_MIN_LENGTH,
)
from app.core.messages import TITLE_CANNOT_BE_NULL
from app.schemas.base import BaseSchema

TaskTitle = Annotated[
    str,
    Field(min_length=TASK_TITLE_MIN_LENGTH, max_length=TASK_TITLE_MAX_LENGTH),
]
TaskDescription = Annotated[
    str,
    Field(max_length=TASK_DESCRIPTION_MAX_LENGTH),
]


class TaskBase(BaseSchema):
    """Base model holding shared task fields."""

    title: TaskTitle
    description: TaskDescription | None = None


class TaskCreate(TaskBase):
    """Schema for creating a task."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TaskUpdate(TaskBase):
    """Schema for updating a whole task (PUT)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TaskPatch(BaseSchema):
    """Schema for partial task update (PATCH)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: TaskTitle | None = None
    description: TaskDescription | None = None

    @field_validator("title", mode="before")
    @classmethod
    def prevent_null_title(cls, value: object) -> object:
        if value is None:
            raise ValueError(TITLE_CANNOT_BE_NULL)
        return value


class TaskRead(BaseSchema):
    """Schema for reading task data."""

    id: int = Field(gt=0)
    title: str
    description: str | None = None


class TaskListResponse(BaseSchema):
    """Response schema for listing tasks with pagination count."""

    items: list[TaskRead]
    total: int = Field(ge=0)
