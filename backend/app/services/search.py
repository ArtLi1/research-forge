import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.models import Paper, PaperChunk, PaperKnowledgeCard, Project, ProjectPaper
from app.providers.chroma import ChromaVectorStore
from app.rag.retrieval import vector_rows
from app.schemas.paper import EvidencePack, EvidencePackItem, SearchRequest


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(self, request: SearchRequest) -> EvidencePack:
        statement = select(Paper)
        if request.scope == "project":
            if request.project_id is None:
                raise AppError("INVALID_SEARCH_SCOPE", "项目检索必须提供 project_id")
            if await self.session.get(Project, request.project_id) is None:
                raise not_found("project", request.project_id)
            statement = statement.join(ProjectPaper, ProjectPaper.paper_id == Paper.id).where(
                ProjectPaper.project_id == request.project_id
            )
        elif request.scope == "papers" and not request.filters.paper_ids:
            raise AppError("INVALID_SEARCH_SCOPE", "指定论文检索必须提供 paper_ids")

        filters = request.filters
        if filters.paper_ids:
            statement = statement.where(Paper.id.in_(filters.paper_ids))
        if filters.year_gte is not None:
            statement = statement.where(Paper.year >= filters.year_gte)
        if filters.year_lte is not None:
            statement = statement.where(Paper.year <= filters.year_lte)
        statement = statement.where(Paper.parse_status.in_(["completed", "partial"]))

        papers = list(await self.session.scalars(statement))
        paper_map = {str(paper.id): paper for paper in papers}
        if not paper_map:
            return EvidencePack(
                query=request.query,
                items=[],
                missing_information=["没有检索到符合范围的正文或知识"],
            )
        store = ChromaVectorStore()
        version_ids = [
            str(item)
            for item in await self.session.scalars(
                select(PaperKnowledgeCard.current_version_id).where(
                    PaperKnowledgeCard.paper_id.in_([paper.id for paper in papers]),
                    PaperKnowledgeCard.current_version_id.is_not(None),
                )
            )
        ]
        await self.session.commit()
        # Only vector calls run concurrently; AsyncSession queries stay sequential.
        knowledge_result, result = await asyncio.gather(
            store.search_knowledge(
                request.query, list(paper_map), min(8, request.top_k), version_ids=version_ids
            ),
            store.search_chunks(request.query, list(paper_map), request.top_k, filters.chunk_types),
        )
        chunk_rows = vector_rows(result)
        active_chunk_ids = set(
            await self.session.scalars(
                select(PaperChunk.chroma_id).where(
                    PaperChunk.paper_id.in_([paper.id for paper in papers]),
                    PaperChunk.chroma_id.in_([row[0] for row in chunk_rows]),
                )
            )
        )
        await self.session.commit()
        items: list[EvidencePackItem] = []
        for _, document, metadata, score in vector_rows(knowledge_result):
            paper = paper_map.get(str(metadata.get("paper_id")))
            if paper is None or metadata.get("knowledge_version_id") not in version_ids:
                continue
            knowledge_type = str(metadata.get("knowledge_type", ""))
            items.append(
                EvidencePackItem(
                    paper_id=paper.id,
                    paper_title=paper.title,
                    year=paper.year,
                    knowledge_type=knowledge_type,
                    name=str(metadata.get("name", "")) or None,
                    content=str(document),
                    section=None,
                    page_start=None,
                    page_end=None,
                    source_type="knowledge_inspiration",
                    score=score,
                )
            )
        for vector_id, document, metadata, score in chunk_rows:
            paper = paper_map.get(str(metadata.get("paper_id")))
            if paper is None or vector_id not in active_chunk_ids:
                continue
            items.append(
                EvidencePackItem(
                    paper_id=paper.id,
                    paper_title=paper.title,
                    year=paper.year,
                    content=str(document),
                    section=metadata.get("section"),
                    page_start=metadata.get("page_start"),
                    page_end=metadata.get("page_end"),
                    score=score,
                )
            )
        deduplicated: list[EvidencePackItem] = []
        seen: set[tuple[uuid.UUID, str]] = set()
        for item in sorted(items, key=lambda value: value.score, reverse=True):
            key = (item.paper_id, item.content)
            if key not in seen:
                seen.add(key)
                deduplicated.append(item)
        return EvidencePack(
            query=request.query,
            items=deduplicated[: request.top_k],
            missing_information=([] if deduplicated else ["没有检索到符合范围的正文或知识"]),
        )
