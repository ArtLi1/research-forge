import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from redis import Redis
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.models import BackgroundTask

TERMINAL_TASK_STATUSES = frozenset({"succeeded", "partial", "failed", "cancelled"})


def task_event_name(status: str) -> str:
    if status in {"succeeded", "partial"}:
        return "completed"
    if status in {"failed", "cancelled"}:
        return status
    return "progress"


def _submit_job(task_type: str, job_path: str, args: tuple[Any, ...], timeout: int) -> str:
    # RQ is synchronous; keep Redis I/O off the API event loop.
    with Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=5, socket_timeout=5
    ) as connection:
        queue = Queue(task_type, connection=connection, default_timeout=timeout)
        return str(queue.enqueue(job_path, *args, job_timeout=timeout).id)


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, task_id: uuid.UUID) -> BackgroundTask:
        task = await self.session.get(BackgroundTask, task_id)
        if task is None:
            raise not_found("task", task_id)
        return task

    async def enqueue(
        self,
        task: BackgroundTask,
        *,
        job_path: str,
        job_timeout: int,
        extra_args: tuple[Any, ...] = (),
    ) -> None:
        if task.resource_id is None:
            raise AppError("TASK_QUEUE_ERROR", "后台任务缺少关联资源", status_code=400)
        try:
            job_id = await asyncio.to_thread(
                _submit_job,
                task.task_type,
                job_path,
                (str(task.resource_id), str(task.id), *extra_args),
                job_timeout,
            )
        except Exception as exc:
            await self.update(
                task.id,
                status="failed",
                stage="enqueue_failed",
                progress=0,
                message="后台任务提交失败",
                error=str(exc)[:4000],
            )
            raise AppError(
                "TASK_QUEUE_ERROR",
                "后台任务提交失败",
                status_code=502,
                details={"reason": str(exc)},
            ) from exc
        task.rq_job_id = job_id
        await self.session.commit()

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
        if status in TERMINAL_TASK_STATUSES:
            task.finished_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(task)
        return task
