import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.models import Paper, PaperKnowledgeCard, PaperKnowledgeVersion
from app.providers.chat import OpenAICompatibleChatProvider, load_prompt
from app.schemas.comparison import ComparisonResult
from app.schemas.knowledge import PaperKnowledgeContent


class ComparisonService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def compare(self, paper_ids: list[uuid.UUID]) -> ComparisonResult:
        if len(set(paper_ids)) != len(paper_ids):
            raise AppError("INVALID_COMPARE_PAPERS", "比较论文不得重复")
        inputs: list[dict[str, object]] = []
        for paper_id in paper_ids:
            paper = await self.session.get(Paper, paper_id)
            if paper is None:
                raise not_found("paper", paper_id)
            card = await self.session.scalar(
                select(PaperKnowledgeCard).where(PaperKnowledgeCard.paper_id == paper_id)
            )
            if card is None or card.current_version_id is None:
                raise AppError(
                    "INSUFFICIENT_KNOWLEDGE",
                    f"论文“{paper.title}”尚无知识卡",
                    status_code=409,
                )
            version = await self.session.get(PaperKnowledgeVersion, card.current_version_id)
            assert version is not None
            content = PaperKnowledgeContent.model_validate(version.content)
            inputs.append(
                {
                    "paper_id": str(paper.id),
                    "title": paper.title,
                    "knowledge": content.model_dump(mode="json"),
                }
            )
        provider = OpenAICompatibleChatProvider()
        result = await provider.generate_structured(
            [
                {"role": "system", "content": load_prompt("compare_papers_v1.md")},
                {
                    "role": "user",
                    "content": json.dumps(inputs, ensure_ascii=False),
                },
            ],
            ComparisonResult,
            temperature=0,
        )
        result.paper_ids = paper_ids
        allowed_paper_ids = set(paper_ids)
        for dimension in result.dimensions:
            dimension.entries = [
                entry for entry in dimension.entries if entry.paper_id in allowed_paper_ids
            ]
        return result
