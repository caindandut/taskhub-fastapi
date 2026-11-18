from __future__ import annotations

from collections.abc import Sequence

from app.core.constants import (
    PROJECT_FORBIDDEN,
    WORKSPACE_FORBIDDEN,
    WORKSPACE_NOT_FOUND,
)
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models import Project, User
from app.models.enums import ProjectStatus, WorkspaceRole
from app.repositories.project import ProjectRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.permissions import load_project_for_user, require_workspace_access


class ProjectService:
    def __init__(
        self,
        repository: ProjectRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.repository = repository
        self.workspace_repository = workspace_repository

    async def create(
        self, workspace_id: int, payload: ProjectCreate, user: User
    ) -> Project:
        workspace = await self.workspace_repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)

        role = await require_workspace_access(
            self.workspace_repository,
            workspace_id,
            user,
            min_role=WorkspaceRole.VIEWER,
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

        await require_workspace_access(
            self.workspace_repository,
            workspace_id,
            user,
            min_role=WorkspaceRole.VIEWER,
            forbidden_message=WORKSPACE_FORBIDDEN,
        )
        return await self.repository.list_by_workspace(workspace_id, status=status)

    async def get(self, project_id: int, user: User) -> Project:
        project, _ = await load_project_for_user(
            self.repository,
            self.workspace_repository,
            project_id,
            user,
            write=False,
        )
        return project

    async def update(
        self, project_id: int, payload: ProjectUpdate, user: User
    ) -> Project:
        project, _ = await load_project_for_user(
            self.repository,
            self.workspace_repository,
            project_id,
            user,
            write=True,
            check_archived=False,
        )
        values = payload.model_dump(exclude_unset=True)
        if not values:
            return project
        return await self.repository.update(project, values)

    async def delete(self, project_id: int, user: User) -> None:
        project, _ = await load_project_for_user(
            self.repository,
            self.workspace_repository,
            project_id,
            user,
            min_role=WorkspaceRole.OWNER,
            check_archived=False,
        )
        await self.repository.delete(project)
