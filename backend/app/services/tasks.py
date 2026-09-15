import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.models import BackgroundTask


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, task_id: uuid.UUID) -> BackgroundTask:
        task = await self.session.get(BackgroundTask, task_id)
        if task is None:
            raise not_found("task", task_id)
        return task

    async def update(
        self,
        task_id: uuid.UUID,
        *,
        status: str,
        stage: str,
        progress: int,
        message: str,
        error: str | None = None,
    ) -> BackgroundTask:
        task = await self.get(task_id)
        task.status = status
        task.stage = stage
        task.progress = progress
        task.message = message
        task.error = error
        if status == "running" and task.started_at is None:
            task.started_at = datetime.now(UTC)
        if status in {"succeeded", "partial", "failed", "cancelled"}:
            task.finished_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(task)
        return task
