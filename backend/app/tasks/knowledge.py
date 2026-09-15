import asyncio
import uuid

from app.db.session import SessionLocal, engine
from app.models import Paper
from app.services.knowledge import KnowledgeService
from app.services.tasks import TaskService


def extract_knowledge_job(paper_id: str, task_id: str) -> None:
    async def run() -> None:
        parsed_paper_id = uuid.UUID(paper_id)
        parsed_task_id = uuid.UUID(task_id)
        async with SessionLocal() as session:
            tasks = TaskService(session)
            try:
                paper = await session.get(Paper, parsed_paper_id)
                if paper is not None:
                    paper.parse_status = "extracting"
                    await session.commit()
                await tasks.update(
                    parsed_task_id,
                    status="running",
                    stage="extracting",
                    progress=85,
                    message="正在分章节提取知识卡",
                )
                knowledge = await KnowledgeService(session).extract(parsed_paper_id)
                if paper is not None:
                    is_partial = bool(paper.parse_error) or knowledge.validation_status == "partial"
                    paper.parse_status = "partial" if is_partial else "completed"
                    await session.commit()
                await tasks.update(
                    parsed_task_id,
                    status="partial" if paper is not None and is_partial else "succeeded",
                    stage="completed",
                    progress=100,
                    message="知识卡、证据和项目知识更新完成",
                    error=paper.parse_error if paper is not None else None,
                )
            except Exception as exc:
                await session.rollback()
                paper = await session.get(Paper, parsed_paper_id)
                if paper is not None:
                    paper.parse_status = "partial"
                    paper.parse_error = str(exc)[:2000]
                    await session.commit()
                await tasks.update(
                    parsed_task_id,
                    status="failed",
                    stage="failed",
                    progress=0,
                    message="知识提取失败",
                    error=str(exc)[:4000],
                )
                raise
            finally:
                await engine.dispose()

    asyncio.run(run())
