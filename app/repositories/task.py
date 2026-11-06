from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_PAGE_SIZE
from app.models import Project, Task, User
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Task, session)

    async def project_exists(self, project_id: int) -> bool:
        return await self.session.get(Project, project_id) is not None

    async def user_exists(self, user_id: int) -> bool:
        return await self.session.get(User, user_id) is not None

    async def search(
        self,
        *,
        q: str | None = None,
        project_id: int | None = None,
        page: int = 1,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> tuple[list[Task], int]:
        filters = []
        if q is not None:
            filters.append(Task.title.icontains(q, autoescape=True))
        if project_id is not None:
            filters.append(Task.project_id == project_id)
        return await self.list(*filters, page=page, limit=limit), await self.count(
            *filters
        )
