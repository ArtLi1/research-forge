import asyncio
import uuid

from app.db.session import engine
from app.services.processing import process_paper


def process_paper_job(paper_id: str, task_id: str) -> None:
    async def run() -> None:
        try:
            await process_paper(uuid.UUID(paper_id), uuid.UUID(task_id))
        finally:
            # SimpleWorker runs jobs serially, while asyncio.run creates a loop per job.
            # Dispose asyncpg connections before that loop closes.
            await engine.dispose()

    asyncio.run(run())
