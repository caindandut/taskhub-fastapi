from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comment
from app.repositories.base import BaseRepository


class CommentRepository(BaseRepository[Comment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Comment, session)

    async def list_by_task(self, task_id: int) -> list[Comment]:
        statement = (
            select(Comment)
            .where(Comment.task_id == task_id)
            .order_by(Comment.created_at, Comment.id)
        )
        return list(await self.session.scalars(statement))
