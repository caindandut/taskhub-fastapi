from app.core.constants import PROJECT_ARCHIVED, PROJECT_FORBIDDEN
from app.core.exceptions import BadRequestException, ForbiddenException
from app.models import Project, User
from app.models.enums import ProjectStatus, UserRole, WorkspaceRole
from app.repositories.workspace import WorkspaceRepository


async def require_project_access(
    workspace_repository: WorkspaceRepository,
    project: Project,
    user: User,
    *,
    write: bool = False,
    allowed_roles: tuple[WorkspaceRole, ...] | None = None,
    forbidden_message: str = PROJECT_FORBIDDEN,
    check_archived: bool = True,
) -> WorkspaceRole:
    """Validate user membership/role on project's workspace and optionally archived status."""
    if user.role == UserRole.ADMIN:
        effective_role = WorkspaceRole.OWNER
    else:
        role = await workspace_repository.get_effective_role(
            project.workspace_id, user.id
        )
        if role is None:
            raise ForbiddenException(forbidden_message)
        if allowed_roles is not None:
            if role not in allowed_roles:
                raise ForbiddenException(forbidden_message)
        elif write and role == WorkspaceRole.VIEWER:
            raise ForbiddenException(forbidden_message)
        effective_role = role

    if write and check_archived and project.status == ProjectStatus.ARCHIVED:
        raise BadRequestException(PROJECT_ARCHIVED)
    return effective_role
