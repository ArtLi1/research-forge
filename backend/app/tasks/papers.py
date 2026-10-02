import asyncio
import uuid
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.models import Paper, PaperChunk, PaperKnowledgeCard, PaperKnowledgeVersion, PaperSection
from app.parsers.pdf import PdfParser
from app.providers.chat import OpenAICompatibleChatProvider
from app.providers.chroma import ChromaVectorStore
from app.rag.chunker import DomainAwareChunker
from app.rag.knowledge import KnowledgeExtractor, stage_knowledge
from app.services.knowledge import KnowledgeService
from app.services.papers import normalize_title
from app.services.tasks import TaskService
from app.tasks.context import TaskContext
from app.tasks.types import TaskKind, TaskStatus

logger = structlog.get_logger()


async def parse_paper(context: TaskContext) -> None:
    await context.progress("parsing", 10, "正在解析 PDF")
    async with context.sessions() as session:
        paper = await session.get(Paper, context.resource_id)
        if paper is None:
            raise not_found("paper", context.resource_id)
        path, year = Path(paper.file_path), paper.year
    parsed = await asyncio.to_thread(PdfParser().parse, path)
    await context.progress("chunking", 35, "正在按章节分块")
    chunks = await asyncio.to_thread(DomainAwareChunker().chunk, parsed)
    if not chunks:
        raise AppError("PAPER_PARSE_FAILED", "没有可用正文块", status_code=422)
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadata: list[dict[str, Any]] = []
    for chunk in chunks:
        value = {
            "paper_id": str(context.resource_id),
            "chunk_type": chunk.chunk_type,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
        }
        if chunk.section_title:
            value["section"] = chunk.section_title
        if year is not None:
            value["year"] = year
        metadata.append(value)
    await context.progress("embedding", 60, "正在生成正文检索索引")
    store = ChromaVectorStore()
    previous_ids = await store.paper_vector_ids(str(context.resource_id))
    # Stage new vectors first. Only the database transaction activates new content.
    await store.index_chunks(
        ids=ids, documents=[item.content for item in chunks], metadatas=metadata
    )
    async with context.transaction() as (session, task):
        paper = await session.scalar(
            select(Paper).where(Paper.id == context.resource_id).with_for_update()
        )
        if paper is None:
            raise not_found("paper", context.resource_id)
        await session.execute(delete(PaperChunk).where(PaperChunk.paper_id == paper.id))
        await session.execute(delete(PaperSection).where(PaperSection.paper_id == paper.id))
        sections: dict[tuple[str, int], uuid.UUID] = {}
        for chunk in chunks:
            if chunk.section_title:
                key = (chunk.section_title, chunk.section_level or 1)
                if key not in sections:
                    section_id = uuid.uuid4()
                    session.add(
                        PaperSection(
                            id=section_id,
                            paper_id=paper.id,
                            title=key[0],
                            level=key[1],
                            order_index=len(sections),
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                        )
                    )
                    sections[key] = section_id
        await session.flush()
        for chunk, vector_id in zip(chunks, ids, strict=True):
            session.add(
                PaperChunk(
                    paper_id=paper.id,
                    section_id=sections.get((chunk.section_title, chunk.section_level or 1))
                    if chunk.section_title
                    else None,
                    chunk_type=chunk.chunk_type,
                    content=chunk.content,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    order_index=chunk.order_index,
                    token_count=chunk.token_count,
                    chroma_id=vector_id,
                )
            )
        title = str(parsed.metadata.get("title") or "").strip()
        if title:
            paper.title, paper.normalized_title = title[:1000], normalize_title(title)[:1000]
        paper.parse_status, paper.parse_error = (
            "extracting",
            "; ".join(parsed.warnings[:10]) or None,
        )
        task.task_type, task.status = TaskKind.KNOWLEDGE_EXTRACT, TaskStatus.QUEUED
        task.rq_job_id = task.lease_token = task.lease_expires_at = task.dispatched_at = None
        task.progress, task.stage, task.message = 75, "extracting", "正文完成，等待提取知识"
        task.attempts = 0
    try:
        # Delete only IDs observed before staging. A later generation may already
        # be indexing this paper after our transaction releases its lease.
        await store.delete_vectors(sorted(set(previous_ids) - set(ids)))
    except Exception:
        logger.exception("stale_chunk_cleanup_failed", paper_id=str(context.resource_id))


async def extract_knowledge(context: TaskContext) -> None:
    await context.progress("extracting", 80, "正在提取场景与算法知识")
    async with context.sessions() as session:
        paper = await session.get(Paper, context.resource_id)
        if paper is None:
            raise not_found("paper", context.resource_id)
        title, warning = paper.title, paper.parse_error
        contents = list(
            await session.scalars(
                select(PaperChunk.content)
                .where(PaperChunk.paper_id == paper.id)
                .order_by(PaperChunk.order_index)
            )
        )
        committed_versions = {
            str(value)
            for value in await session.scalars(
                select(PaperKnowledgeVersion.id)
                .join(PaperKnowledgeCard, PaperKnowledgeCard.id == PaperKnowledgeVersion.card_id)
                .where(PaperKnowledgeCard.paper_id == paper.id)
            )
        }
    if not contents:
        raise AppError("KNOWLEDGE_EXTRACTION_FAILED", "论文尚无正文块", status_code=409)
    settings = get_settings()
    provider = OpenAICompatibleChatProvider(
        model=settings.llm_extraction_model or settings.llm_model
    )
    extractor = KnowledgeExtractor(provider, max_chars=settings.knowledge_batch_chars)
    content = await extractor.extract(title, contents)
    await context.progress("indexing_knowledge", 92, "正在保存知识检索索引")
    version_id, store = uuid.uuid4(), ChromaVectorStore()
    previous_ids = await store.paper_vector_ids(str(context.resource_id), knowledge=True)
    active_ids = await stage_knowledge(store, context.resource_id, version_id, content)
    async with context.transaction() as (session, task):
        await KnowledgeService(session).save(
            context.resource_id,
            version_id,
            content,
            model=provider.model,
            prompt_version=extractor.prompt.version,
        )
        paper = await session.get(Paper, context.resource_id)
        if paper is None:
            raise not_found("paper", context.resource_id)
        paper.parse_status = "partial" if warning else "completed"
        TaskService.finish(
            task,
            TaskStatus.PARTIAL if warning else TaskStatus.SUCCEEDED,
            "论文知识提取完成",
            error=warning,
        )
    try:
        # Preserve committed history: in-flight research snapshots can still
        # reference it. Only abandoned staging generations are garbage.
        stale_ids = [
            key
            for key in previous_ids
            if key.split(":", 1)[0] not in committed_versions and key not in active_ids
        ]
        await store.delete_vectors(stale_ids, knowledge=True)
    except Exception:
        logger.exception("stale_knowledge_cleanup_failed", paper_id=str(context.resource_id))
