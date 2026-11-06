from collections.abc import Mapping
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.constants import DEFAULT_PAGE_SIZE
from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get(self, identifier: int) -> ModelT | None:
        return await self.session.get(self.model, identifier)

    async def create(self, instance: ModelT) -> ModelT:
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def list(
        self,
        *filters: ColumnElement[bool],
        page: int = 1,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> list[ModelT]:
        statement = (
            select(self.model)
            .where(*filters)
            .order_by(*self.model.__mapper__.primary_key)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(await self.session.scalars(statement))

    async def count(self, *filters: ColumnElement[bool]) -> int:
        statement = select(func.count()).select_from(self.model).where(*filters)
        return (await self.session.execute(statement)).scalar_one()

    async def update(self, instance: ModelT, values: Mapping[str, object]) -> ModelT:
        for field, value in values.items():
            setattr(instance, field, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()
