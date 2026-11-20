from datetime import datetime
from typing import Annotated, Literal

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
    DEFAULT_PAGE_SIZE,
    FIELD_CANNOT_BE_NULL,
    MAX_PAGE_SIZE,
    WORKSPACE_NAME_MAX_LENGTH,
    WORKSPACE_NAME_MIN_LENGTH,
)
from app.models.enums import WorkspaceRole

MemberAssignableRole = Literal[WorkspaceRole.EDITOR, WorkspaceRole.VIEWER]

WorkspaceName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=WORKSPACE_NAME_MIN_LENGTH,
        max_length=WORKSPACE_NAME_MAX_LENGTH,
    ),
]


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: WorkspaceName


class WorkspaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: WorkspaceName | None = None

    @field_validator("name")
    @classmethod
    def reject_explicit_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError(FIELD_CANNOT_BE_NULL)
        return value


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: PositiveInt
    name: str
    owner_id: PositiveInt
    created_at: datetime


class WorkspaceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    q: str | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)


class WorkspacePage(BaseModel):
    items: list[WorkspaceRead]
    total: int = Field(ge=0)
    page: PositiveInt
    limit: PositiveInt


class WorkspaceMemberCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: PositiveInt
    role: MemberAssignableRole = WorkspaceRole.VIEWER


class WorkspaceMemberUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MemberAssignableRole


class WorkspaceMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: PositiveInt
    user_id: PositiveInt
    role: WorkspaceRole
    email: EmailStr | None = None
    full_name: str | None = None
