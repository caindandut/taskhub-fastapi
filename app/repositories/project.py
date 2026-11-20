from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.models.enums import ProjectStatus
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Project, session)

    async def list_by_workspace(
        self,
        workspace_id: int,
        status: ProjectStatus | None = None,
    ) -> Sequence[Project]:
        statement = select(Project).where(Project.workspace_id == workspace_id)
        if status is not None:
            statement = statement.where(Project.status == status)
        statement = statement.order_by(Project.id)
        return (await self.session.scalars(statement)).all()
