from app.core.constants import (
    PROJECT_ARCHIVED,
    PROJECT_FORBIDDEN,
    PROJECT_NOT_FOUND,
    TASK_FORBIDDEN,
    TASK_NOT_FOUND,
    WORKSPACE_FORBIDDEN,
)
from app.core.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.models import Project, Task, User
from app.models.enums import ProjectStatus, UserRole, WorkspaceRole
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.repositories.workspace import WorkspaceRepository

_ROLE_RANK = {
    WorkspaceRole.VIEWER: 1,
    WorkspaceRole.EDITOR: 2,
    WorkspaceRole.OWNER: 3,
}


async def require_workspace_access(
    workspace_repository: WorkspaceRepository,
    workspace_id: int,
    user: User,
    *,
    min_role: WorkspaceRole = WorkspaceRole.VIEWER,
    forbidden_message: str = WORKSPACE_FORBIDDEN,
) -> WorkspaceRole:
    """Validate that user has at least `min_role` in the workspace."""
    if user.role == UserRole.ADMIN:
        return WorkspaceRole.OWNER

    role = await workspace_repository.get_effective_role(workspace_id, user.id)
    if role is None or _ROLE_RANK[role] < _ROLE_RANK[min_role]:
        raise ForbiddenException(forbidden_message)
    return role


async def require_project_access(
    workspace_repository: WorkspaceRepository,
    project: Project,
    user: User,
    *,
    write: bool = False,
    min_role: WorkspaceRole | None = None,
    forbidden_message: str = PROJECT_FORBIDDEN,
    check_archived: bool = True,
) -> WorkspaceRole:
    """Validate user role on project's workspace and optionally archived status."""
    required_role = min_role or (
        WorkspaceRole.EDITOR if write else WorkspaceRole.VIEWER
    )
    effective_role = await require_workspace_access(
        workspace_repository,
        project.workspace_id,
        user,
        min_role=required_role,
        forbidden_message=forbidden_message,
    )

    if write and check_archived and project.status == ProjectStatus.ARCHIVED:
        raise BadRequestException(PROJECT_ARCHIVED)
    return effective_role


async def load_project_for_user(
    project_repository: ProjectRepository,
    workspace_repository: WorkspaceRepository,
    project_id: int,
    user: User,
    *,
    write: bool = False,
    min_role: WorkspaceRole | None = None,
    forbidden_message: str = PROJECT_FORBIDDEN,
    check_archived: bool = True,
) -> tuple[Project, WorkspaceRole]:
    """Load project (or 404) and enforce user's access level."""
    project = await project_repository.get(project_id)
    if project is None:
        raise NotFoundException(PROJECT_NOT_FOUND)
    role = await require_project_access(
        workspace_repository,
        project,
        user,
        write=write,
        min_role=min_role,
        forbidden_message=forbidden_message,
        check_archived=check_archived,
    )
    return project, role


async def load_task_for_user(
    task_repository: TaskRepository,
    project_repository: ProjectRepository,
    workspace_repository: WorkspaceRepository,
    task_id: int,
    user: User,
    *,
    write: bool = False,
    forbidden_message: str = TASK_FORBIDDEN,
    check_archived: bool = True,
) -> tuple[Task, Project, WorkspaceRole]:
    """Load task (or 404), its project, and enforce user's access level."""
    task = await task_repository.get(task_id)
    if task is None:
        raise NotFoundException(TASK_NOT_FOUND)
    project, role = await load_project_for_user(
        project_repository,
        workspace_repository,
        task.project_id,
        user,
        write=write,
        forbidden_message=forbidden_message,
        check_archived=check_archived,
    )
    return task, project, role
