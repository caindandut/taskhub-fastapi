from typing import Annotated, Literal

from pydantic import (
    ConfigDict,
    EmailStr,
    PositiveInt,
    StringConstraints,
    field_validator,
)

from app.core.constants import (
    WORKSPACE_NAME_MAX_LENGTH,
    WORKSPACE_NAME_MIN_LENGTH,
)
from app.models.enums import WorkspaceRole
from app.schemas.base import (
    BaseSchema,
    PaginatedPage,
    PaginationQuery,
    UtcDatetime,
    require_not_null,
)

MemberAssignableRole = Literal[WorkspaceRole.EDITOR, WorkspaceRole.VIEWER]

WorkspaceName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=WORKSPACE_NAME_MIN_LENGTH,
        max_length=WORKSPACE_NAME_MAX_LENGTH,
    ),
]


class WorkspaceCreate(BaseSchema):
    name: WorkspaceName


class WorkspaceUpdate(BaseSchema):
    name: WorkspaceName | None = None

    @field_validator("name")
    @classmethod
    def reject_explicit_null(cls, value: str | None) -> str:
        return require_not_null(value)


class WorkspaceRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: PositiveInt
    name: str
    owner_id: PositiveInt
    created_at: UtcDatetime


class WorkspaceQuery(PaginationQuery):
    q: str | None = None


class WorkspacePage(PaginatedPage):
    items: list[WorkspaceRead]


class WorkspaceMemberCreate(BaseSchema):
    user_id: PositiveInt
    role: MemberAssignableRole = WorkspaceRole.VIEWER


class WorkspaceMemberUpdate(BaseSchema):
    role: MemberAssignableRole


class WorkspaceMemberRead(BaseSchema):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: PositiveInt
    user_id: PositiveInt
    role: WorkspaceRole
    email: EmailStr | None = None
    full_name: str | None = None
