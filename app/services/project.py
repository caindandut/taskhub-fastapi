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

    async def _get_membership_role(
        self, workspace_id: int, user: User
    ) -> WorkspaceRole | None:
        if user.role == UserRole.ADMIN:
            return WorkspaceRole.OWNER
        return await self.workspace_repository.get_effective_role(workspace_id, user.id)

    async def create(
        self, workspace_id: int, payload: ProjectCreate, user: User
    ) -> Project:
        workspace = await self.workspace_repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)

        if user.role != UserRole.ADMIN:
            role = await self._get_membership_role(workspace_id, user)
            if role is None:
                raise ForbiddenException(WORKSPACE_FORBIDDEN)
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

        if user.role != UserRole.ADMIN:
            role = await self._get_membership_role(workspace_id, user)
            if role is None:
                raise ForbiddenException(WORKSPACE_FORBIDDEN)

        return await self.repository.list_by_workspace(workspace_id, status=status)

    async def get(self, project_id: int, user: User) -> Project:
        project = await self.repository.get(project_id)
        if project is None:
            raise NotFoundException(PROJECT_NOT_FOUND)

        if user.role != UserRole.ADMIN:
            role = await self._get_membership_role(project.workspace_id, user)
            if role is None:
                raise ForbiddenException(PROJECT_FORBIDDEN)

        return project

    async def update(
        self, project_id: int, payload: ProjectUpdate, user: User
    ) -> Project:
        project = await self.repository.get(project_id)
        if project is None:
            raise NotFoundException(PROJECT_NOT_FOUND)

        if user.role != UserRole.ADMIN:
            role = await self._get_membership_role(project.workspace_id, user)
            if role is None or role == WorkspaceRole.VIEWER:
                raise ForbiddenException(PROJECT_FORBIDDEN)

        values = payload.model_dump(exclude_unset=True)
        if not values:
            return project
        return await self.repository.update(project, values)

    async def delete(self, project_id: int, user: User) -> None:
        project = await self.repository.get(project_id)
        if project is None:
            raise NotFoundException(PROJECT_NOT_FOUND)

        if user.role != UserRole.ADMIN:
            role = await self._get_membership_role(project.workspace_id, user)
            if role != WorkspaceRole.OWNER:
                raise ForbiddenException(PROJECT_FORBIDDEN)

        await self.repository.delete(project)
