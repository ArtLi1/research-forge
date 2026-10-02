import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.models import BackgroundTask
from app.services.tasks import TaskService
from app.tasks.types import TaskStatus

logger = structlog.get_logger()


async def dispatch_once(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        await TaskService(session).recover()
        ids = list(
            await session.scalars(
                select(BackgroundTask.id)
                .where(
                    BackgroundTask.status == TaskStatus.QUEUED,
                    or_(
                        BackgroundTask.dispatched_at.is_(None),
                        BackgroundTask.dispatched_at < datetime.now(UTC) - timedelta(seconds=30),
                    ),
                )
                .order_by(BackgroundTask.created_at)
                .limit(20)
            )
        )
        await session.rollback()
    semaphore = asyncio.Semaphore(4)

    async def dispatch(task_id: uuid.UUID) -> None:
        async with semaphore, sessions() as session:
            await TaskService(session).dispatch(task_id)

    async with asyncio.TaskGroup() as group:
        for task_id in ids:
            group.create_task(dispatch(task_id))


async def dispatcher_loop(sessions: async_sessionmaker[AsyncSession]) -> None:
    while True:
        try:
            await dispatch_once(sessions)
        except Exception:
            logger.exception("task_dispatcher_failed")
        await asyncio.sleep(get_settings().task_dispatch_seconds)
