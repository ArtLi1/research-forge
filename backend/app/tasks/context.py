import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import BackgroundTask
from app.services.tasks import TaskService
from app.tasks.types import TaskKind


@dataclass(frozen=True, slots=True)
class TaskContext:
    task_id: uuid.UUID
    token: uuid.UUID
    resource_id: uuid.UUID
    kind: TaskKind
    payload: dict[str, Any]
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[tuple[AsyncSession, BackgroundTask]]:
        async with self.sessions() as session, session.begin():
            task = await TaskService(session).lock_owned(self.task_id, self.token)
            yield session, task

    async def progress(self, stage: str, progress: int, message: str) -> None:
        async with self.transaction() as (_, task):
            task.stage, task.message = stage, message
            task.progress = max(task.progress, min(99, max(0, progress)))
            task.lease_expires_at = datetime.now(UTC) + timedelta(
                seconds=get_settings().task_lease_seconds
            )

    async def renew(self) -> None:
        async with self.transaction() as (_, task):
            task.lease_expires_at = datetime.now(UTC) + timedelta(
                seconds=get_settings().task_lease_seconds
            )
