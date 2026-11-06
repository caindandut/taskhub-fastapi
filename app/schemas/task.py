from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, field_validator

from app.core.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    TASK_DESCRIPTION_MAX_LENGTH,
    TASK_TITLE_MAX_LENGTH,
    TASK_TITLE_MIN_LENGTH,
)
from app.models.enums import TaskPriority, TaskStatus

TaskTitle = Annotated[
    str, Field(min_length=TASK_TITLE_MIN_LENGTH, max_length=TASK_TITLE_MAX_LENGTH)
]
TaskDescription = Annotated[str, Field(max_length=TASK_DESCRIPTION_MAX_LENGTH)]


class TaskFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: TaskTitle
    description: TaskDescription | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: PositiveInt | None = None
    due_date: datetime | None = Field(default=None, description="Due date in UTC")

    @field_validator("due_date")
    @classmethod
    def normalize_due_date(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None:
            return value.astimezone(UTC).replace(tzinfo=None)
        return value


class TaskCreate(TaskFields):
    project_id: PositiveInt
    created_by: PositiveInt


class TaskUpdate(TaskFields):
    title: TaskTitle | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None

    @field_validator("title", "status", "priority")
    @classmethod
    def reject_explicit_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class TaskRead(TaskCreate):
    model_config = ConfigDict(from_attributes=True)

    id: PositiveInt
    created_at: datetime


class TaskQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: TaskTitle | None = None
    project_id: PositiveInt | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class TaskPage(BaseModel):
    items: list[TaskRead]
    total: int = Field(ge=0)
    page: PositiveInt
    limit: PositiveInt
