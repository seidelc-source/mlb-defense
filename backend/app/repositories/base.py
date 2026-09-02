from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, id)

    async def get_or_raise(self, id: uuid.UUID) -> ModelT:
        from app.core.exceptions import NotFoundError
        obj = await self.get(id)
        if obj is None:
            raise NotFoundError(self.model.__tablename__, id)
        return obj

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        filters: list[Any] | None = None,
    ) -> list[ModelT]:
        stmt = select(self.model)
        if filters:
            stmt = stmt.where(*filters)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, filters: list[Any] | None = None) -> int:
        stmt = select(func.count()).select_from(self.model)
        if filters:
            stmt = stmt.where(*filters)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(self, **kwargs: Any) -> ModelT:
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, obj: ModelT, **kwargs: Any) -> ModelT:
        for key, value in kwargs.items():
            setattr(obj, key, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def upsert(self, lookup: dict[str, Any], defaults: dict[str, Any]) -> tuple[ModelT, bool]:
        """Get-or-create with field updates. Returns (obj, created)."""
        filters = [getattr(self.model, k) == v for k, v in lookup.items()]
        stmt = select(self.model).where(*filters)
        result = await self.session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            obj = await self.create(**lookup, **defaults)
            return obj, True
        await self.update(obj, **defaults)
        return obj, False

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()
