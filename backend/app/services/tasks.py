import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from redis import Redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.models import AgentRun, BackgroundTask, Paper
from app.tasks.types import TASK_SPECS, TERMINAL_STATUSES, TaskKind, TaskStatus

logger = structlog.get_logger()


class LeaseLost(AppError):
    def __init__(self) -> None:
        super().__init__("TASK_LEASE_LOST", "任务执行权已失效", status_code=409)


def _submit_job(kind: TaskKind, task_id: uuid.UUID, generation: int, existing: str | None) -> str:
    with Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=5, socket_timeout=5
    ) as connection:
        if existing:
            try:
                job = Job.fetch(existing, connection=connection)
                if job.get_status(refresh=True) in {
                    JobStatus.QUEUED,
                    JobStatus.STARTED,
                    JobStatus.DEFERRED,
                    JobStatus.SCHEDULED,
                }:
                    return existing
            except NoSuchJobError:
                pass
        job_id = f"{task_id}-{generation}"
        queue = Queue(str(kind), connection=connection, default_timeout=TASK_SPECS[kind].timeout)
        job = queue.enqueue(
            "app.tasks.runner.execute_task",
            str(task_id),
            generation,
            job_id=job_id,
            job_timeout=TASK_SPECS[kind].timeout,
            result_ttl=86400,
            failure_ttl=604800,
        )
        return str(job.id)


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, task_id: uuid.UUID) -> BackgroundTask:
        task = await self.session.get(BackgroundTask, task_id)
        if task is None:
            raise not_found("task", task_id)
        return task

    async def lock(self, task_id: uuid.UUID) -> BackgroundTask:
        task = await self.session.scalar(
            select(BackgroundTask)
            .where(BackgroundTask.id == task_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if task is None:
            raise not_found("task", task_id)
        return task

    async def lock_owned(self, task_id: uuid.UUID, token: uuid.UUID) -> BackgroundTask:
        task = await self.lock(task_id)
        now = datetime.now(UTC)
        expires = task.lease_expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if (
            task.status != TaskStatus.RUNNING
            or task.lease_token != token
            or not expires
            or expires <= now
        ):
            raise LeaseLost()
        return task

    async def claim(self, task_id: uuid.UUID, generation: int) -> BackgroundTask | None:
        task = await self.lock(task_id)
        if task.status != TaskStatus.QUEUED or task.dispatch_count != generation:
            return None
        now = datetime.now(UTC)
        task.status = TaskStatus.RUNNING
        task.started_at = task.started_at or now
        task.attempts += 1
        task.error = None
        task.lease_token = uuid.uuid4()
        task.lease_expires_at = now + timedelta(seconds=get_settings().task_lease_seconds)
        await self.session.commit()
        return task

    async def dispatch(self, task_id: uuid.UUID) -> BackgroundTask:
        task = await self.lock(task_id)
        if task.status != TaskStatus.QUEUED:
            return task
        try:
            kind = TaskKind(task.task_type)
            if task.resource_id is None or task.resource_type != TASK_SPECS[kind].resource_type:
                raise ValueError("Task resource mismatch")
        except ValueError:
            self.finish(task, TaskStatus.FAILED, "任务资源与类型不匹配", error="无效任务")
            await self.session.commit()
            await self.session.refresh(task)
            return task
        generation = task.dispatch_count + 1
        try:
            job_id = await asyncio.to_thread(_submit_job, kind, task.id, generation, task.rq_job_id)
        except Exception:
            # The committed row is the durable dispatch record, never lose accepted work.
            logger.exception("task_dispatch_failed", task_id=str(task.id))
            task.message = "队列暂不可用，任务已保存，等待重新派发"
            task.dispatched_at = datetime.now(UTC)
            await self.session.commit()
            await self.session.refresh(task)
            return task
        if job_id != task.rq_job_id:
            task.dispatch_count = generation
            task.rq_job_id = job_id
        task.dispatched_at = datetime.now(UTC)
        task.message = "等待后台处理"
        await self.session.commit()
        await self.session.refresh(task)
        return task

    @staticmethod
    def finish(
        task: BackgroundTask, status: TaskStatus, message: str, *, error: str | None = None
    ) -> None:
        if status not in TERMINAL_STATUSES:
            raise ValueError("Expected terminal task status")
        task.status, task.stage, task.message, task.error = status, str(status), message, error
        task.progress = (
            100 if status in {TaskStatus.SUCCEEDED, TaskStatus.PARTIAL} else task.progress
        )
        task.finished_at = datetime.now(UTC)
        task.lease_token = task.lease_expires_at = None
        task.active_key = None

    async def recover(self) -> int:
        rows = list(
            await self.session.scalars(
                select(BackgroundTask)
                .where(
                    BackgroundTask.status == TaskStatus.RUNNING,
                    or_(
                        BackgroundTask.lease_expires_at <= datetime.now(UTC),
                        BackgroundTask.lease_expires_at.is_(None),
                    ),
                )
                .with_for_update(skip_locked=True)
                .limit(100)
            )
        )
        for task in rows:
            if task.attempts >= get_settings().task_max_attempts:
                self.finish(
                    task,
                    TaskStatus.FAILED,
                    "任务多次失去执行心跳，请检查后台服务",
                    error="执行租约过期",
                )
                run = await self.session.scalar(select(AgentRun).where(AgentRun.task_id == task.id))
                if run is not None:
                    run.status, run.error, run.finished_at = "failed", task.error, task.finished_at
                if task.resource_type == "paper" and task.resource_id:
                    paper = await self.session.get(Paper, task.resource_id)
                    if paper is not None:
                        paper.parse_status = (
                            "partial" if task.task_type == TaskKind.KNOWLEDGE_EXTRACT else "failed"
                        )
                        paper.parse_error = task.error
            else:
                task.status, task.rq_job_id = TaskStatus.QUEUED, None
                task.lease_token = task.lease_expires_at = None
                task.dispatched_at = None
                task.message = "执行中断，正在恢复任务"
        await self.session.commit()
        return len(rows)
