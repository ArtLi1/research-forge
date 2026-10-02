import asyncio
import math
import uuid
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.providers.chroma import ChromaVectorStore


class RetrievalScope(BaseModel):
    paper_ids: list[str] = Field(default_factory=list)
    knowledge_version_ids: list[str] = Field(default_factory=list)


class KnowledgeItem(BaseModel):
    id: str
    paper_id: uuid.UUID
    knowledge_type: Literal["scenario", "algorithm"]
    name: str
    content: str
    score: float = Field(ge=0, le=1)
    source_type: Literal["knowledge_inspiration"] = "knowledge_inspiration"


class KnowledgeStore(Protocol):
    async def search_knowledge(
        self,
        query: str,
        allowed_paper_ids: list[str],
        top_k: int = 8,
        knowledge_type: str | None = None,
        *,
        version_ids: list[str] | None = None,
    ) -> dict[str, Any]: ...


def vector_rows(result: dict[str, Any]) -> list[tuple[str, str, dict[str, Any], float]]:
    columns = [
        (result.get(key) or [[]])[0] for key in ("ids", "documents", "metadatas", "distances")
    ]
    if len({len(column) for column in columns}) != 1:
        raise AppError("VECTOR_INDEX_ERROR", "检索结果结构不完整", status_code=502)
    rows = []
    for key, document, metadata, distance in zip(*columns, strict=True):
        if not isinstance(metadata, dict) or not isinstance(document, str) or not document.strip():
            continue
        try:
            score = 1.0 - float(distance)
        except (TypeError, ValueError):
            continue
        if math.isfinite(score):
            rows.append((str(key), str(document), metadata, min(1.0, max(0.0, score))))
    return rows


class KnowledgeRetriever:
    def __init__(self, store: KnowledgeStore | None = None, *, concurrency: int = 3) -> None:
        self.store = store or ChromaVectorStore()
        self.semaphore = asyncio.Semaphore(concurrency)

    async def search(
        self,
        scope: RetrievalScope,
        query: str,
        kind: Literal["scenario", "algorithm"],
        *,
        limit: int = 15,
    ) -> list[KnowledgeItem]:
        if not scope.paper_ids or not scope.knowledge_version_ids:
            return []
        async with self.semaphore:
            result = await self.store.search_knowledge(
                query,
                scope.paper_ids,
                top_k=limit,
                knowledge_type=kind,
                version_ids=scope.knowledge_version_ids,
            )
        items = []
        for key, content, metadata, score in vector_rows(result):
            if str(metadata.get("paper_id")) not in scope.paper_ids:
                continue
            if str(metadata.get("knowledge_version_id")) not in scope.knowledge_version_ids:
                continue
            if metadata.get("knowledge_type") != kind:
                continue
            try:
                items.append(
                    KnowledgeItem(
                        id=key,
                        paper_id=uuid.UUID(str(metadata["paper_id"])),
                        knowledge_type=kind,
                        name=str(metadata.get("name", "")),
                        content=content,
                        score=score,
                    )
                )
            except ValueError:
                continue
        return items[:limit]

    async def retrieve(
        self,
        scope: RetrievalScope,
        queries: list[str],
        kind: Literal["scenario", "algorithm"],
        *,
        limit: int = 15,
    ) -> list[KnowledgeItem]:
        results = await asyncio.gather(
            *(self.search(scope, query, kind, limit=limit) for query in dict.fromkeys(queries))
        )
        unique: dict[str, KnowledgeItem] = {}
        for items in results:
            for item in items:
                if item.id not in unique or item.score > unique[item.id].score:
                    unique[item.id] = item
        return sorted(unique.values(), key=lambda item: (-item.score, item.id))[:limit]
