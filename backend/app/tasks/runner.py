import asyncio
import uuid
from contextlib import suppress

import structlog
from sqlalchemy import select

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging
from app.db.session import Database
from app.models import AgentRun, Paper
from app.services.tasks import LeaseLost, TaskService
from app.tasks.context import TaskContext
from app.tasks.types import TASK_SPECS, TaskKind, TaskStatus

logger = structlog.get_logger()


async def run_task(database: Database, task_id: uuid.UUID, generation: int) -> None:
    from app.agents.runtime import generate_research
    from app.tasks.papers import extract_knowledge, parse_paper

    handlers = {
        TaskKind.PAPER_PARSE: parse_paper,
        TaskKind.KNOWLEDGE_EXTRACT: extract_knowledge,
        TaskKind.SCHEME_GENERATE: generate_research,
    }
    async with database.sessions() as session:
        task = await TaskService(session).claim(task_id, generation)
        if task is None:
            return
        if task.resource_id is None or task.lease_token is None:
            raise RuntimeError("Claimed task has no execution identity")
        context = TaskContext(
            task.id,
            task.lease_token,
            task.resource_id,
            TaskKind(task.task_type),
            dict(task.payload),
            database.sessions,
        )
    structlog.contextvars.bind_contextvars(task_id=str(task_id), task_type=str(context.kind))

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(get_settings().task_heartbeat_seconds)
            await context.renew()

    work = asyncio.create_task(handlers[context.kind](context))
    heartbeats = asyncio.create_task(heartbeat())
    try:
        async with asyncio.timeout(TASK_SPECS[context.kind].timeout):
            done, _ = await asyncio.wait({work, heartbeats}, return_when=asyncio.FIRST_COMPLETED)
            if work in done:
                await work
            else:
                await heartbeats
        logger.info("task_completed")
    except LeaseLost:
        logger.warning("task_lease_lost")
    except Exception as exc:
        logger.exception("task_failed")
        message = exc.message if isinstance(exc, AppError) else "后台处理失败，请检查服务日志后重试"
        with suppress(LeaseLost):
            async with context.transaction() as (session, task):
                TaskService.finish(task, TaskStatus.FAILED, message, error=message)
                run = await session.scalar(select(AgentRun).where(AgentRun.task_id == task.id))
                if run is not None:
                    run.status, run.error, run.finished_at = "failed", message, task.finished_at
                if task.resource_type == "paper":
                    paper = await session.get(Paper, context.resource_id)
                    if paper is not None:
                        paper.parse_status = (
                            "partial" if context.kind == TaskKind.KNOWLEDGE_EXTRACT else "failed"
                        )
                        paper.parse_error = message
        raise
    finally:
        for future in (work, heartbeats):
            future.cancel()
        await asyncio.gather(work, heartbeats, return_exceptions=True)
        structlog.contextvars.clear_contextvars()


def execute_task(task_id: str, generation: int) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    async def execute() -> None:
        database = Database(settings.database_url, worker=True)
        try:
            await run_task(database, uuid.UUID(task_id), generation)
        finally:
            await database.close()

    asyncio.run(execute())
