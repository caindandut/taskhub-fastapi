from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comment
from app.repositories.base import BaseRepository
from app.schemas.comment import CommentQuery


class CommentRepository(BaseRepository[Comment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Comment, session)

    async def list_by_task(
        self, task_id: int, query: CommentQuery
    ) -> tuple[list[Comment], int]:
        statement = (
            select(Comment)
            .where(Comment.task_id == task_id)
            .order_by(Comment.created_at, Comment.id)
            .offset((query.page - 1) * query.limit)
            .limit(query.limit)
        )
        items = list(await self.session.scalars(statement))
        total = await self.count(Comment.task_id == task_id)
        return items, total
