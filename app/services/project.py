from __future__ import annotations

from collections.abc import Sequence

from app.core.constants import (
    PROJECT_FORBIDDEN,
    PROJECT_NOT_FOUND,
    WORKSPACE_FORBIDDEN,
    WORKSPACE_NOT_FOUND,
)
from app.core.exceptions import (
    ForbiddenException,
    NotFoundException,
)
from app.models import Project, User
from app.models.enums import ProjectStatus, UserRole, WorkspaceRole
from app.repositories.project import ProjectRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.repository = repository
        self.workspace_repository = workspace_repository

    async def _require_workspace_role(
        self,
        workspace_id: int,
        user: User,
        *,
        allowed_roles: tuple[WorkspaceRole, ...] | None = None,
        forbidden_message: str = PROJECT_FORBIDDEN,
    ) -> WorkspaceRole:
        if user.role == UserRole.ADMIN:
            return WorkspaceRole.OWNER
        role = await self.workspace_repository.get_effective_role(workspace_id, user.id)
        if role is None or (allowed_roles is not None and role not in allowed_roles):
            raise ForbiddenException(forbidden_message)
        return role

    async def create(
        self, workspace_id: int, payload: ProjectCreate, user: User
    ) -> Project:
        workspace = await self.workspace_repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)

        role = await self._require_workspace_role(
            workspace_id,
            user,
            forbidden_message=WORKSPACE_FORBIDDEN,
        )
        if role == WorkspaceRole.VIEWER:
            raise ForbiddenException(PROJECT_FORBIDDEN)

        project = Project(
            workspace_id=workspace_id,
            name=payload.name,
            description=payload.description,
            status=ProjectStatus.ACTIVE,
        )
        return await self.repository.create(project)

    async def list_by_workspace(
        self,
        workspace_id: int,
        user: User,
        status: ProjectStatus | None = None,
    ) -> Sequence[Project]:
        workspace = await self.workspace_repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)

        await self._require_workspace_role(
            workspace_id,
            user,
            forbidden_message=WORKSPACE_FORBIDDEN,
        )
        return await self.repository.list_by_workspace(workspace_id, status=status)

    async def get(self, project_id: int, user: User) -> Project:
        project = await self.repository.get(project_id)
        if project is None:
            raise NotFoundException(PROJECT_NOT_FOUND)

        await self._require_workspace_role(project.workspace_id, user)
        return project

    async def update(
        self, project_id: int, payload: ProjectUpdate, user: User
    ) -> Project:
        project = await self.repository.get(project_id)
        if project is None:
            raise NotFoundException(PROJECT_NOT_FOUND)

        await self._require_workspace_role(
            project.workspace_id,
            user,
            allowed_roles=(WorkspaceRole.OWNER, WorkspaceRole.EDITOR),
        )

        values = payload.model_dump(exclude_unset=True)
        if not values:
            return project
        return await self.repository.update(project, values)

    async def delete(self, project_id: int, user: User) -> None:
        project = await self.repository.get(project_id)
        if project is None:
            raise NotFoundException(PROJECT_NOT_FOUND)

        await self._require_workspace_role(
            project.workspace_id,
            user,
            allowed_roles=(WorkspaceRole.OWNER,),
        )
        await self.repository.delete(project)
