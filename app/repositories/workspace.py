from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import DEFAULT_PAGE_SIZE
from app.models import User, Workspace, WorkspaceMember
from app.models.enums import WorkspaceRole
from app.repositories.base import BaseRepository


class WorkspaceRepository(BaseRepository[Workspace]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Workspace, session)

    async def user_exists(self, user_id: int) -> bool:
        return await self.session.get(User, user_id) is not None

    async def search_for_user(
        self,
        *,
        user_id: int,
        is_admin: bool = False,
        q: str | None = None,
        page: int = 1,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[Sequence[Workspace], int]:
        filters = []
        if not is_admin:
            filters.append(
                or_(
                    Workspace.owner_id == user_id,
                    Workspace.members.any(WorkspaceMember.user_id == user_id),
                )
            )
        if q is not None:
            filters.append(Workspace.name.icontains(q, autoescape=True))

        count_stmt = select(func.count(Workspace.id)).where(*filters)
        total = (await self.session.execute(count_stmt)).scalar_one()

        statement = (
            select(Workspace)
            .where(*filters)
            .order_by(Workspace.id)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        workspaces = (await self.session.scalars(statement)).all()
        return workspaces, total

    async def is_member(self, workspace_id: int, user_id: int) -> bool:
        statement = select(
            select(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
            .exists()
        )
        return bool(await self.session.scalar(statement))

    async def get_member(
        self, workspace_id: int, user_id: int
    ) -> WorkspaceMember | None:
        statement = (
            select(WorkspaceMember)
            .options(selectinload(WorkspaceMember.user))
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return await self.session.scalar(statement)

    async def get_member_role(
        self, workspace_id: int, user_id: int
    ) -> WorkspaceRole | None:
        statement = select(WorkspaceMember.role).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
        return await self.session.scalar(statement)

    async def list_members(self, workspace_id: int) -> Sequence[WorkspaceMember]:
        statement = (
            select(WorkspaceMember)
            .options(selectinload(WorkspaceMember.user))
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.user_id)
        )
        return (await self.session.scalars(statement)).all()

    async def add_member(
        self,
        workspace_id: int,
        user_id: int,
        role: WorkspaceRole = WorkspaceRole.VIEWER,
    ) -> WorkspaceMember:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        self.session.add(member)
        await self.session.flush()
        # Refresh with user relationship loaded
        statement = (
            select(WorkspaceMember)
            .options(selectinload(WorkspaceMember.user))
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        return (await self.session.scalars(statement)).one()

    async def update_member_role(
        self, member: WorkspaceMember, role: WorkspaceRole
    ) -> WorkspaceMember:
        member.role = role
        await self.session.flush()
        await self.session.refresh(member)
        return member

    async def delete_member(self, member: WorkspaceMember) -> None:
        await self.session.delete(member)
        await self.session.flush()
