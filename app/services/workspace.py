from __future__ import annotations

from app.core.constants import (
    CANNOT_MODIFY_WORKSPACE_OWNER,
    CANNOT_REMOVE_WORKSPACE_OWNER,
    MEMBER_ALREADY_EXISTS,
    MEMBER_NOT_FOUND,
    USER_NOT_FOUND,
    WORKSPACE_FORBIDDEN,
    WORKSPACE_NOT_FOUND,
)
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models import User, Workspace, WorkspaceMember
from app.models.enums import UserRole, WorkspaceRole
from app.repositories.workspace import WorkspaceRepository
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceMemberRead,
    WorkspaceMemberUpdate,
    WorkspacePage,
    WorkspaceQuery,
    WorkspaceRead,
    WorkspaceUpdate,
)


class WorkspaceService:
    def __init__(self, repository: WorkspaceRepository) -> None:
        self.repository = repository

    async def _check_workspace_access(
        self, workspace: Workspace, user: User, require_owner: bool = False
    ) -> None:
        if user.role == UserRole.ADMIN:
            return

        role = await self.repository.get_member_role(workspace.id, user.id)
        if role is None:
            raise ForbiddenException(WORKSPACE_FORBIDDEN)

        if (
            require_owner
            and role != WorkspaceRole.OWNER
            and workspace.owner_id != user.id
        ):
            raise ForbiddenException(WORKSPACE_FORBIDDEN)

    def _to_member_read(self, member: WorkspaceMember) -> WorkspaceMemberRead:
        return WorkspaceMemberRead(
            workspace_id=member.workspace_id,
            user_id=member.user_id,
            role=member.role,
            email=member.user.email if member.user else None,
            full_name=member.user.full_name if member.user else None,
        )

    async def create(self, payload: WorkspaceCreate, owner: User) -> Workspace:
        workspace = await self.repository.create(
            Workspace(name=payload.name, owner_id=owner.id)
        )
        await self.repository.add_member(workspace.id, owner.id, WorkspaceRole.OWNER)
        return workspace

    async def list(self, query: WorkspaceQuery, user: User) -> WorkspacePage:
        is_admin = user.role == UserRole.ADMIN
        workspaces, total = await self.repository.search_for_user(
            user_id=user.id,
            is_admin=is_admin,
            q=query.q,
            page=query.page,
            limit=query.limit,
        )
        return WorkspacePage(
            items=[WorkspaceRead.model_validate(w) for w in workspaces],
            total=total,
            page=query.page,
            limit=query.limit,
        )

    async def get(self, workspace_id: int, user: User) -> Workspace:
        workspace = await self.repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)
        await self._check_workspace_access(workspace, user, require_owner=False)
        return workspace

    async def update(
        self, workspace_id: int, payload: WorkspaceUpdate, user: User
    ) -> Workspace:
        workspace = await self.repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)
        await self._check_workspace_access(workspace, user, require_owner=True)

        values = payload.model_dump(exclude_unset=True)
        if not values:
            return workspace
        return await self.repository.update(workspace, values)

    async def delete(self, workspace_id: int, user: User) -> None:
        workspace = await self.repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)
        await self._check_workspace_access(workspace, user, require_owner=True)
        await self.repository.delete(workspace)

    async def list_members(
        self, workspace_id: int, user: User
    ) -> list[WorkspaceMemberRead]:
        workspace = await self.repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)
        await self._check_workspace_access(workspace, user, require_owner=False)

        members = await self.repository.list_members(workspace_id)
        return [self._to_member_read(m) for m in members]

    async def add_member(
        self, workspace_id: int, payload: WorkspaceMemberCreate, user: User
    ) -> WorkspaceMemberRead:
        workspace = await self.repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)
        await self._check_workspace_access(workspace, user, require_owner=True)

        if not await self.repository.user_exists(payload.user_id):
            raise NotFoundException(USER_NOT_FOUND)

        if await self.repository.is_member(workspace_id, payload.user_id):
            raise ConflictException(MEMBER_ALREADY_EXISTS)

        member = await self.repository.add_member(
            workspace_id, payload.user_id, payload.role
        )
        return self._to_member_read(member)

    async def update_member_role(
        self,
        workspace_id: int,
        target_user_id: int,
        payload: WorkspaceMemberUpdate,
        user: User,
    ) -> WorkspaceMemberRead:
        workspace = await self.repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)
        await self._check_workspace_access(workspace, user, require_owner=True)

        member = await self.repository.get_member(workspace_id, target_user_id)
        if member is None:
            raise NotFoundException(MEMBER_NOT_FOUND)

        if workspace.owner_id == target_user_id and payload.role != WorkspaceRole.OWNER:
            raise BadRequestException(CANNOT_MODIFY_WORKSPACE_OWNER)

        member = await self.repository.update_member_role(member, payload.role)
        return self._to_member_read(member)

    async def remove_member(
        self, workspace_id: int, target_user_id: int, user: User
    ) -> None:
        workspace = await self.repository.get(workspace_id)
        if workspace is None:
            raise NotFoundException(WORKSPACE_NOT_FOUND)

        member = await self.repository.get_member(workspace_id, target_user_id)
        if member is None:
            raise NotFoundException(MEMBER_NOT_FOUND)

        if workspace.owner_id == target_user_id:
            raise BadRequestException(CANNOT_REMOVE_WORKSPACE_OWNER)

        # Allow if user is self (leaving workspace), or user is workspace owner/admin
        if user.id != target_user_id:
            await self._check_workspace_access(workspace, user, require_owner=True)

        await self.repository.delete_member(member)
