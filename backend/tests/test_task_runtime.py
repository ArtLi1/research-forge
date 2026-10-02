import asyncio
import threading
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.errors import AppError
from app.models import BackgroundTask
from app.services import tasks
from app.services.tasks import LeaseLost, TaskService
from app.tasks.context import TaskContext
from app.tasks.dispatcher import dispatch_once
from app.tasks.types import TaskKind


async def add_task(database, **kwargs):
    task = BackgroundTask(
        task_type="paper_parse", resource_type="paper", resource_id=uuid.uuid4(), **kwargs
    )
    async with database.transaction() as session:
        session.add(task)
    return task


async def test_dispatch_runs_redis_off_event_loop(database, monkeypatch):
    task = await add_task(database)
    caller_thread = threading.get_ident()
    captured = []

    def submit(*args):
        assert threading.get_ident() != caller_thread
        captured.append(args)
        return "job-id"

    monkeypatch.setattr(tasks, "_submit_job", submit)
    async with database.sessions() as session:
        await TaskService(session).dispatch(task.id)
        result = await session.get(BackgroundTask, task.id)
        assert (result.rq_job_id, result.dispatch_count) == ("job-id", 1)
    assert captured == [(TaskKind.PAPER_PARSE, task.id, 1, None)]


async def test_queue_outage_is_durable_and_dispatcher_retries(database, monkeypatch):
    task = await add_task(database)

    def fail(*_):
        raise ConnectionError("redis unavailable")

    monkeypatch.setattr(tasks, "_submit_job", fail)
    async with database.sessions() as session:
        await TaskService(session).dispatch(task.id)
        row = await session.get(BackgroundTask, task.id)
        assert row.status == "queued"
        assert row.finished_at is None and row.dispatch_count == 0
        row.dispatched_at = None
        await session.commit()
    monkeypatch.setattr(tasks, "_submit_job", lambda *args: "recovered-job")
    await dispatch_once(database.sessions)
    async with database.sessions() as session:
        row = await session.get(BackgroundTask, task.id)
        assert row.rq_job_id == "recovered-job"


async def test_generation_fence_and_duplicate_claim(database):
    task = await add_task(database, dispatch_count=2)
    async with database.sessions() as session:
        service = TaskService(session)
        assert await service.claim(task.id, 1) is None
        await session.rollback()
        claimed = await service.claim(task.id, 2)
        assert claimed and claimed.lease_token
        assert claimed.attempts == 1
        assert await service.claim(task.id, 2) is None


async def test_postgres_concurrent_claim_has_single_owner(database):
    if database.engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL row locks; CI uses isolated schemas")
    task = await add_task(database, dispatch_count=1)

    async def claim():
        async with database.sessions() as session:
            result = await TaskService(session).claim(task.id, 1)
            return result.lease_token if result else None

    results = await asyncio.gather(*(claim() for _ in range(5)))
    assert sum(token is not None for token in results) == 1


async def test_lease_recovery_fences_old_worker_and_exhausts_attempts(database):
    task = await add_task(database, dispatch_count=1)
    async with database.sessions() as session:
        claimed = await TaskService(session).claim(task.id, 1)
        token = claimed.lease_token
        claimed.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        await TaskService(session).recover()
    context = TaskContext(
        task.id, token, task.resource_id, TaskKind.PAPER_PARSE, {}, database.sessions
    )
    with pytest.raises(LeaseLost):
        await context.progress("late", 70, "迟到写入")
    async with database.transaction() as session:
        row = await session.get(BackgroundTask, task.id)
        assert row.status == "queued"
        row.status = "running"
        row.attempts = 3
        row.active_key = f"paper:{row.resource_id}"
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    async with database.sessions() as session:
        await TaskService(session).recover()
        row = await session.get(BackgroundTask, task.id)
        assert row.status == "failed" and row.finished_at
        assert row.active_key is None


async def test_terminal_task_never_regresses(database):
    task = await add_task(database, status="succeeded", progress=100)
    context = TaskContext(
        task.id, uuid.uuid4(), task.resource_id, TaskKind.PAPER_PARSE, {}, database.sessions
    )
    with pytest.raises(LeaseLost):
        await context.progress("parsing", 1, "迟到更新")
    async with database.sessions() as session:
        row = await session.get(BackgroundTask, task.id)
        assert row.status == "succeeded" and row.progress == 100


def test_submit_job_closes_connection_and_uses_unified_runner(monkeypatch):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    redis = MagicMock()
    redis.from_url.return_value = connection
    queue = MagicMock()
    queue.return_value.enqueue.return_value.id = "job-id"
    monkeypatch.setattr(tasks, "Redis", redis)
    monkeypatch.setattr(tasks, "Queue", queue)
    monkeypatch.setattr(tasks, "get_settings", lambda: SimpleNamespace(redis_url="redis://test"))
    task_id = uuid.uuid4()
    assert tasks._submit_job(TaskKind.PAPER_PARSE, task_id, 3, None) == "job-id"
    connection.__exit__.assert_called_once()
    call = queue.return_value.enqueue.call_args
    assert call.args == ("app.tasks.runner.execute_task", str(task_id), 3)
    assert call.kwargs["job_id"] == f"{task_id}-3"


@pytest.mark.parametrize(
    "status,event",
    [
        ("succeeded", "completed"),
        ("partial", "completed"),
        ("failed", "failed"),
        ("cancelled", "cancelled"),
    ],
)
async def test_terminal_sse_ends_stream(database, status, event):
    from app.main import create_app

    task = await add_task(database, status=status)
    async with AsyncClient(
        transport=ASGITransport(app=create_app(database=database, dispatch_tasks=False)),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/tasks/{task.id}/events")
    assert response.status_code == 200
    assert response.text.startswith(f"event: {event}\n")
    assert response.text.count("event:") == 1


async def test_missing_task_rejected_before_streaming(database):
    from app.main import create_app

    async with AsyncClient(
        transport=ASGITransport(app=create_app(database=database, dispatch_tasks=False)),
        base_url="http://test",
    ) as client:
        response = await client.get(f"/api/v1/tasks/{uuid.uuid4()}/events")
        invalid = await client.get("/api/v1/tasks/not-a-uuid")
    assert response.status_code == 404
    assert invalid.status_code == 422
    assert "input" not in invalid.json()["error"]["details"]["errors"][0]
    assert "X-Request-ID" in response.headers


async def test_unknown_failed_task_cannot_be_retried_as_paper_parse():
    from app.api.v1.tasks import retry_task

    task = BackgroundTask(
        id=uuid.uuid4(),
        status="failed",
        task_type="unknown",
        resource_type="paper",
        resource_id=uuid.uuid4(),
    )
    session = AsyncMock()
    session.get.return_value = task
    with pytest.raises(AppError) as error:
        await retry_task(task.id, session)
    assert error.value.code == "TASK_NOT_RETRYABLE"
