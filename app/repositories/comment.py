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
        return await self.paginate(
            Comment.task_id == task_id,
            page=query.page,
            limit=query.limit,
            order_by=(Comment.created_at, Comment.id),
        )
