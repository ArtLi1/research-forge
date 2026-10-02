from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


class Database:
    def __init__(self, url: str, *, worker: bool = False, schema: str | None = None) -> None:
        if worker:
            self.engine = create_async_engine(url, poolclass=NullPool)
        else:
            self.engine = create_async_engine(url, pool_pre_ping=True)
        if schema:
            self.engine = self.engine.execution_options(schema_translate_map={None: schema})
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session, session.begin():
            yield session

    async def close(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.sessions() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
