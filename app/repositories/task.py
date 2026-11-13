from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_PAGE_SIZE
from app.models import Project, Task, User, Workspace, WorkspaceMember
from app.models.enums import TaskPriority, TaskStatus
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Task, session)

    async def project_exists(self, project_id: int) -> bool:
        return await self.session.get(Project, project_id) is not None

    async def get_project(self, project_id: int) -> Project | None:
        return await self.session.get(Project, project_id)

    async def user_exists(self, user_id: int) -> bool:
        return await self.session.get(User, user_id) is not None

    async def search(
        self,
        *,
        user_id: int | None = None,
        is_admin: bool = False,
        q: str | None = None,
        project_id: int | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: int | None = None,
        page: int = 1,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[Task], int]:
        filters = []
        if not is_admin and user_id is not None:
            accessible_projects = (
                select(Project.id)
                .join(Workspace, Project.workspace_id == Workspace.id)
                .where(
                    or_(
                        Workspace.owner_id == user_id,
                        Workspace.members.any(WorkspaceMember.user_id == user_id),
                    )
                )
            )
            filters.append(Task.project_id.in_(accessible_projects))
        if q is not None:
            filters.append(Task.title.icontains(q, autoescape=True))
        if project_id is not None:
            filters.append(Task.project_id == project_id)
        if status is not None:
            filters.append(Task.status == status)
        if priority is not None:
            filters.append(Task.priority == priority)
        if assignee_id is not None:
            filters.append(Task.assignee_id == assignee_id)
        return await self.list(*filters, page=page, limit=limit), await self.count(
            *filters
        )
