import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.models import (
    Evidence,
    Paper,
    PaperChunk,
    PaperKnowledgeCard,
    PaperKnowledgeVersion,
)
from app.providers.chat import OpenAICompatibleChatProvider, load_prompt
from app.providers.chroma import ChromaVectorStore
from app.schemas.knowledge import (
    AlgorithmKnowledge,
    KnowledgeCardRead,
    PaperKnowledgeContent,
    ScenarioKnowledge,
)


def merge_knowledge(parts: list[PaperKnowledgeContent]) -> PaperKnowledgeContent:
    scenarios: dict[str, ScenarioKnowledge] = {}
    algorithms: dict[str, AlgorithmKnowledge] = {}
    for part in parts:
        for scenario in part.scenarios:
            key = KnowledgeService._normalize(scenario.name)
            if key not in scenarios or _completeness(scenario) > _completeness(scenarios[key]):
                scenarios[key] = scenario.model_copy(deep=True)
        for algorithm in part.algorithms:
            key = KnowledgeService._normalize(algorithm.name)
            if key not in algorithms or _completeness(algorithm) > _completeness(
                algorithms[key]
            ):
                algorithms[key] = algorithm.model_copy(deep=True)
    return PaperKnowledgeContent(
        scenarios=list(scenarios.values()), algorithms=list(algorithms.values())
    )


def _completeness(item: ScenarioKnowledge | AlgorithmKnowledge) -> int:
    return sum(len(str(value).strip()) for value in item.model_dump().values() if value)


class KnowledgeService:
    prompt_version = "extract_paper_knowledge_v2"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, paper_id: uuid.UUID) -> KnowledgeCardRead:
        card = await self.session.scalar(
            select(PaperKnowledgeCard).where(PaperKnowledgeCard.paper_id == paper_id)
        )
        if card is None or card.current_version_id is None:
            raise AppError("KNOWLEDGE_NOT_FOUND", "论文尚无知识卡", status_code=404)
        version = await self.session.get(PaperKnowledgeVersion, card.current_version_id)
        if version is None:
            raise AppError("KNOWLEDGE_NOT_FOUND", "知识卡当前版本不存在", status_code=404)
        return KnowledgeCardRead(
            card_id=card.id,
            paper_id=paper_id,
            version_id=version.id,
            version_number=version.version_number,
            status=card.status,
            validation_status=version.validation_status,
            extraction_model=version.extraction_model,
            prompt_version=version.prompt_version,
            content=PaperKnowledgeContent.model_validate(version.content),
            created_at=version.created_at,
        )

    async def evidence(self, paper_id: uuid.UUID) -> list[Evidence]:
        if await self.session.get(Paper, paper_id) is None:
            raise not_found("paper", paper_id)
        result = await self.session.scalars(
            select(Evidence)
            .where(Evidence.paper_id == paper_id)
            .order_by(Evidence.created_at, Evidence.field_path)
        )
        return list(result)

    async def extract(self, paper_id: uuid.UUID) -> KnowledgeCardRead:
        paper = await self.session.get(Paper, paper_id)
        if paper is None:
            raise not_found("paper", paper_id)
        chunks = list(
            await self.session.scalars(
                select(PaperChunk)
                .where(PaperChunk.paper_id == paper_id)
                .order_by(PaperChunk.order_index)
            )
        )
        if not chunks:
            raise AppError(
                "KNOWLEDGE_EXTRACTION_FAILED",
                "论文没有可用于知识提取的正文块",
                status_code=409,
            )
        settings = get_settings()
        provider = OpenAICompatibleChatProvider(
            model=settings.llm_extraction_model or settings.llm_model
        )
        prompt = load_prompt("extract_paper_knowledge_v1.md")
        parts: list[PaperKnowledgeContent] = []
        for batch in self._batches(chunks):
            parts.append(
                await provider.generate_structured(
                    [
                        {"role": "system", "content": prompt},
                        {
                            "role": "user",
                            "content": f"论文：{paper.title}\n\n片段：\n{batch}",
                        },
                    ],
                    PaperKnowledgeContent,
                    temperature=0,
                )
            )
        content = merge_knowledge(parts)
        card = await self.session.scalar(
            select(PaperKnowledgeCard).where(PaperKnowledgeCard.paper_id == paper_id)
        )
        if card is None:
            card = PaperKnowledgeCard(
                paper_id=paper_id, status="generated", current_version_id=None
            )
            self.session.add(card)
            await self.session.flush()
        current_max = await self.session.scalar(
            select(func.coalesce(func.max(PaperKnowledgeVersion.version_number), 0)).where(
                PaperKnowledgeVersion.card_id == card.id
            )
        )
        next_version = int(current_max or 0) + 1
        version = PaperKnowledgeVersion(
            card_id=card.id,
            version_number=next_version,
            content=content.model_dump(mode="json"),
            extraction_model=provider.model,
            prompt_version=self.prompt_version,
            validation_status="passed",
        )
        self.session.add(version)
        await self.session.flush()
        card.current_version_id = version.id
        card.status = "generated"
        await self.session.commit()
        await self.session.refresh(version)
        await self._index(paper_id, version.id, content)
        return await self.get(paper_id)

    @staticmethod
    def _batches(chunks: list[PaperChunk], max_chars: int = 14000) -> list[str]:
        batches: list[str] = []
        current: list[str] = []
        size = 0
        for chunk in chunks:
            text = chunk.content
            if current and size + len(text) > max_chars:
                batches.append("\n\n".join(current))
                current, size = [], 0
            current.append(text)
            size += len(text)
        if current:
            batches.append("\n\n".join(current))
        return batches

    async def _index(
        self,
        paper_id: uuid.UUID,
        version_id: uuid.UUID,
        content: PaperKnowledgeContent,
    ) -> None:
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, object]] = []
        entries: list[tuple[str, ScenarioKnowledge | AlgorithmKnowledge, str]] = []
        entries.extend(
            (
                "scenario",
                item,
                (
                    f"{item.name}\n\n{item.description}\n\nChallenge:\n{item.key_challenge}"
                    f"\n\nInnovation:\n{item.innovation_point or ''}"
                ),
            )
            for item in content.scenarios
        )
        entries.extend(
            (
                "algorithm",
                item,
                (
                    f"{item.name}\n\nCore idea:\n{item.core_idea}"
                    f"\n\nMechanism:\n{item.key_mechanism}"
                    f"\n\nInnovation:\n{item.innovation_point}"
                ),
            )
            for item in content.algorithms
        )
        type_indexes = {"scenario": 0, "algorithm": 0}
        for knowledge_type, item, document in entries:
            index = type_indexes[knowledge_type]
            type_indexes[knowledge_type] += 1
            ids.append(f"{version_id}:{knowledge_type}:{index}")
            documents.append(document)
            metadatas.append(
                {
                    "paper_id": str(paper_id),
                    "knowledge_version_id": str(version_id),
                    "knowledge_type": knowledge_type,
                    "item_index": index,
                    "name": item.name,
                }
            )
        await ChromaVectorStore().index_knowledge(
            paper_id=str(paper_id),
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip().lower()
