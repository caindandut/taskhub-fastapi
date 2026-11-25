import builtins
from collections.abc import Mapping, Sequence
from typing import Any, Generic, TypeVar

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
        order_by: Sequence[Any] | None = None,
    ) -> list[ModelT]:
        order_clauses = order_by or self.model.__mapper__.primary_key
        statement = (
            select(self.model)
            .where(*filters)
            .order_by(*order_clauses)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(await self.session.scalars(statement))

    async def count(self, *filters: ColumnElement[bool]) -> int:
        statement = select(func.count()).select_from(self.model).where(*filters)
        return (await self.session.execute(statement)).scalar_one()

    async def paginate(
        self,
        *filters: ColumnElement[bool],
        page: int = 1,
        limit: int = DEFAULT_PAGE_SIZE,
        order_by: Sequence[Any] | None = None,
    ) -> tuple[builtins.list[ModelT], int]:
        """Return paginated rows while skipping COUNT(*) on partial pages."""
        items = await self.list(*filters, page=page, limit=limit, order_by=order_by)
        if len(items) < limit and (page == 1 or len(items) > 0):
            return items, (page - 1) * limit + len(items)
        return items, await self.count(*filters)

    async def update(self, instance: ModelT, values: Mapping[str, object]) -> ModelT:
        for field, value in values.items():
            setattr(instance, field, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        await self.session.delete(instance)
        await self.session.flush()
