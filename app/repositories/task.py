from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models import Project, Task, User, Workspace
from app.repositories.base import BaseRepository
from app.repositories.workspace import WorkspaceRepository
from app.schemas.task import TaskQuery


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Task, session)

    async def get_user(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def user_exists(self, user_id: int) -> bool:
        return await self.get_user(user_id) is not None

    async def search(
        self,
        query: TaskQuery,
        *,
        user_id: int,
        is_admin: bool = False,
    ) -> tuple[list[Task], int]:
        filters: list[ColumnElement[bool]] = []
        if not is_admin:
            accessible_projects = (
                select(Project.id)
                .join(Workspace, Project.workspace_id == Workspace.id)
                .where(WorkspaceRepository.accessible_workspace_filter(user_id))
            )
            filters.append(Task.project_id.in_(accessible_projects))
        if query.q is not None:
            filters.append(Task.title.icontains(query.q, autoescape=True))
        if query.project_id is not None:
            filters.append(Task.project_id == query.project_id)
        if query.status is not None:
            filters.append(Task.status == query.status)
        if query.priority is not None:
            filters.append(Task.priority == query.priority)
        if query.assignee_id is not None:
            filters.append(Task.assignee_id == query.assignee_id)
        return (
            await self.list(*filters, page=query.page, limit=query.limit),
            await self.count(*filters),
        )
