from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Label, task_labels
from app.repositories.base import BaseRepository


class LabelRepository(BaseRepository[Label]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Label, session)

    async def list_by_project(self, project_id: int) -> list[Label]:
        statement = (
            select(Label).where(Label.project_id == project_id).order_by(Label.id)
        )
        return list(await self.session.scalars(statement))

    async def get_by_project_and_name(self, project_id: int, name: str) -> Label | None:
        statement = select(Label).where(
            Label.project_id == project_id,
            func.lower(Label.name) == name.lower(),
        )
        return await self.session.scalar(statement)

    async def list_for_task(self, task_id: int) -> list[Label]:
        statement = (
            select(Label)
            .join(task_labels, Label.id == task_labels.c.label_id)
            .where(task_labels.c.task_id == task_id)
            .order_by(Label.id)
        )
        return list(await self.session.scalars(statement))

    async def is_attached_to_task(self, task_id: int, label_id: int) -> bool:
        statement = select(
            select(task_labels)
            .where(
                task_labels.c.task_id == task_id,
                task_labels.c.label_id == label_id,
            )
            .exists()
        )
        return bool(await self.session.scalar(statement))

    async def attach_to_task(self, task_id: int, label_id: int) -> None:
        await self.session.execute(
            insert(task_labels).values(task_id=task_id, label_id=label_id)
        )
        await self.session.flush()

    async def detach_from_task(self, task_id: int, label_id: int) -> None:
        await self.session.execute(
            delete(task_labels).where(
                task_labels.c.task_id == task_id,
                task_labels.c.label_id == label_id,
            )
        )
        await self.session.flush()
