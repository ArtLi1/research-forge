import asyncio
import uuid

from app.agents.scheme_agent import SchemeAgent
from app.db.session import SessionLocal, engine
from app.schemas.scheme import SchemeGenerateRequest
from app.services.tasks import TaskService


def generate_schemes_job(
    project_id: str,
    task_id: str,
    payload: dict[str, object],
) -> None:
    async def run() -> None:
        parsed_project_id = uuid.UUID(project_id)
        parsed_task_id = uuid.UUID(task_id)
        try:
            async with SessionLocal() as session:
                tasks = TaskService(session)
                try:
                    candidate_ids = await SchemeAgent(
                        session,
                        parsed_project_id,
                        SchemeGenerateRequest.model_validate(payload),
                        parsed_task_id,
                    ).run()
                    await tasks.update(
                        parsed_task_id,
                        status="succeeded",
                        stage="completed",
                        progress=100,
                        message=f"已生成 {len(candidate_ids)} 个候选研究方案",
                    )
                except Exception as exc:
                    await session.rollback()
                    await tasks.update(
                        parsed_task_id,
                        status="failed",
                        stage="failed",
                        progress=0,
                        message="候选方案生成失败",
                        error=str(exc)[:4000],
                    )
                    raise
        finally:
            await engine.dispose()

    asyncio.run(run())
