import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import SessionLocal, get_session
from app.schemas.scheme import SchemeGenerateRequest
from app.schemas.task import TaskRead
from app.services.papers import PaperService
from app.services.schemes import SchemeService
from app.services.tasks import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> object:
    return await TaskService(session).get(task_id)


@router.get("/{task_id}/events")
async def task_events(task_id: uuid.UUID, request: Request) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        last_payload = ""
        while not await request.is_disconnected():
            async with SessionLocal() as session:
                task = await TaskService(session).get(task_id)
                payload = TaskRead.model_validate(task).model_dump_json()
            if payload != last_payload:
                event = (
                    "completed"
                    if task.status in {"succeeded", "partial"}
                    else "failed"
                    if task.status == "failed"
                    else "progress"
                )
                yield f"event: {event}\ndata: {payload}\n\n"
                last_payload = payload
            if task.status in {"succeeded", "partial", "failed", "cancelled"}:
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{task_id}/retry", response_model=TaskRead, status_code=202)
async def retry_task(task_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> object:
    task = await TaskService(session).get(task_id)
    if task.status != "failed" or task.resource_id is None:
        raise AppError("TASK_NOT_RETRYABLE", "该任务当前不可重试", status_code=409)
    if task.task_type == "scheme_generate":
        if task.resource_type != "project":
            raise AppError("TASK_NOT_RETRYABLE", "该任务当前不可重试", status_code=409)
        return await SchemeService(session).start_generation(
            task.resource_id,
            SchemeGenerateRequest.model_validate(task.payload),
        )
    if task.resource_type != "paper":
        raise AppError("TASK_NOT_RETRYABLE", "该任务当前不可重试", status_code=409)
    if task.task_type == "knowledge_extract":
        return await PaperService(session).extract(task.resource_id)
    return await PaperService(session).reparse(task.resource_id)
