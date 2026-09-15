import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Paper, PaperKnowledgeCard


class PaperRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self, *, knowledge_ready: bool = False) -> list[Paper]:
        query = select(Paper).order_by(Paper.created_at.desc())
        if knowledge_ready:
            query = query.join(
                PaperKnowledgeCard,
                PaperKnowledgeCard.paper_id == Paper.id,
            ).where(PaperKnowledgeCard.current_version_id.is_not(None))
        result = await self.session.scalars(query)
        return list(result)

    async def get(self, paper_id: uuid.UUID) -> Paper | None:
        return await self.session.get(Paper, paper_id)

    async def by_hash(self, file_hash: str) -> Paper | None:
        return await self.session.scalar(select(Paper).where(Paper.file_hash == file_hash))

    async def add(self, paper: Paper) -> Paper:
        self.session.add(paper)
        await self.session.flush()
        return paper
