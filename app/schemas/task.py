from datetime import UTC, datetime
from typing import Annotated

from pydantic import ConfigDict, Field, PositiveInt, field_validator

from app.core.constants import (
    TASK_DESCRIPTION_MAX_LENGTH,
    TASK_TITLE_MAX_LENGTH,
    TASK_TITLE_MIN_LENGTH,
)
from app.models.enums import TaskPriority, TaskStatus
from app.schemas.base import (
    BaseSchema,
    PaginatedPage,
    PaginationQuery,
    UtcDatetime,
    require_not_null,
)

TaskTitle = Annotated[
    str, Field(min_length=TASK_TITLE_MIN_LENGTH, max_length=TASK_TITLE_MAX_LENGTH)
]
TaskDescription = Annotated[str, Field(max_length=TASK_DESCRIPTION_MAX_LENGTH)]


def _normalize_input_due_date(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


class TaskFields(BaseSchema):
    title: TaskTitle
    description: TaskDescription | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: PositiveInt | None = None
    due_date: datetime | None = Field(default=None, description="Due date in UTC")


class TaskBase(TaskFields):
    @field_validator("due_date")
    @classmethod
    def normalize_due_date(cls, value: datetime | None) -> datetime | None:
        return _normalize_input_due_date(value)


class TaskCreate(TaskBase):
    project_id: PositiveInt


class ProjectTaskCreate(TaskBase):
    pass


class TaskUpdate(BaseSchema):
    title: TaskTitle | None = None
    description: TaskDescription | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: PositiveInt | None = None
    due_date: datetime | None = Field(default=None, description="Due date in UTC")

    @field_validator("due_date")
    @classmethod
    def normalize_due_date(cls, value: datetime | None) -> datetime | None:
        return _normalize_input_due_date(value)

    @field_validator("title", "status", "priority")
    @classmethod
    def reject_explicit_null(cls, value: str | None) -> str:
        return require_not_null(value)


class TaskRead(TaskFields):
    model_config = ConfigDict(from_attributes=True)

    id: PositiveInt
    project_id: PositiveInt
    created_by: PositiveInt
    due_date: UtcDatetime | None = Field(default=None, description="Due date in UTC")
    created_at: UtcDatetime


class ProjectTaskQuery(PaginationQuery):
    q: TaskTitle | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: PositiveInt | None = None


class TaskQuery(ProjectTaskQuery):
    project_id: PositiveInt | None = None


class TaskPage(PaginatedPage):
    items: list[TaskRead]
