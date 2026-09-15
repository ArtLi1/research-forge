import asyncio
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete

from app.core.errors import AppError
from app.db.session import SessionLocal
from app.models import Paper, PaperChunk, PaperSection
from app.parsers.pdf import PdfParser
from app.providers.chroma import ChromaVectorStore
from app.rag.chunker import DomainAwareChunker
from app.services.papers import normalize_title
from app.services.tasks import TaskService


async def process_paper(paper_id: uuid.UUID, task_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        tasks = TaskService(session)
        paper = await session.get(Paper, paper_id)
        if paper is None:
            await tasks.update(
                task_id,
                status="failed",
                stage="failed",
                progress=0,
                message="论文不存在",
                error=f"paper {paper_id} not found",
            )
            return
        try:
            paper.parse_status = "parsing"
            await session.commit()
            await tasks.update(
                task_id,
                status="running",
                stage="parsing",
                progress=10,
                message="正在解析 PDF",
            )
            parsed = await asyncio.to_thread(PdfParser().parse, Path(paper.file_path))

            paper.parse_status = "chunking"
            await session.commit()
            await tasks.update(
                task_id,
                status="running",
                stage="chunking",
                progress=40,
                message="正在按章节分块",
            )
            chunks = await asyncio.to_thread(DomainAwareChunker().chunk, parsed)
            if not chunks:
                raise AppError("PAPER_PARSE_FAILED", "解析后没有可用正文块")

            vector_store = ChromaVectorStore()
            await vector_store.delete_paper_chunks(str(paper.id))
            await session.execute(delete(PaperChunk).where(PaperChunk.paper_id == paper.id))
            await session.execute(delete(PaperSection).where(PaperSection.paper_id == paper.id))
            await session.flush()

            section_map: dict[tuple[str, int], uuid.UUID] = {}
            section_order = 0
            for chunk in chunks:
                if chunk.section_title is None:
                    continue
                key = (chunk.section_title, chunk.section_level or 1)
                if key not in section_map:
                    section = PaperSection(
                        paper_id=paper.id,
                        title=chunk.section_title,
                        level=chunk.section_level or 1,
                        order_index=section_order,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                    )
                    session.add(section)
                    await session.flush()
                    section_map[key] = section.id
                    section_order += 1

            rows: list[PaperChunk] = []
            metadatas: list[dict[str, Any]] = []
            for chunk in chunks:
                chroma_id = str(uuid.uuid4())
                section_key = (
                    (chunk.section_title, chunk.section_level or 1) if chunk.section_title else None
                )
                row = PaperChunk(
                    paper_id=paper.id,
                    section_id=section_map.get(section_key) if section_key else None,
                    chunk_type=chunk.chunk_type,
                    content=chunk.content,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    order_index=chunk.order_index,
                    token_count=chunk.token_count,
                    chroma_id=chroma_id,
                )
                rows.append(row)
                metadata: dict[str, Any] = {
                    "paper_id": str(paper.id),
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "chunk_type": chunk.chunk_type,
                    "language": "unknown",
                }
                if chunk.section_title:
                    metadata["section"] = chunk.section_title
                if paper.year is not None:
                    metadata["year"] = paper.year
                metadatas.append(metadata)
            session.add_all(rows)
            await session.commit()

            paper.parse_status = "embedding"
            await session.commit()
            await tasks.update(
                task_id,
                status="running",
                stage="embedding",
                progress=70,
                message="正在生成默认向量并写入 Chroma",
            )
            await vector_store.index_chunks(
                ids=[row.chroma_id for row in rows],
                documents=[row.content for row in rows],
                metadatas=metadatas,
            )

            metadata_title = str(parsed.metadata.get("title") or "").strip()
            if metadata_title:
                paper.title = metadata_title
                paper.normalized_title = normalize_title(metadata_title)
            paper.parse_status = "extracting"
            paper.parse_error = "; ".join(parsed.warnings[:10]) or None
            await session.commit()
            task = await tasks.update(
                task_id,
                status="running",
                stage="extracting",
                progress=80,
                message="PDF 解析完成，等待知识提取",
            )
            # Reuse the upload task id so the existing SSE connection follows the queue handoff.
            task.task_type = "knowledge_extract"
            await session.commit()
            from app.services.papers import PaperService

            await PaperService(session).enqueue(
                task,
                job_path="app.tasks.knowledge.extract_knowledge_job",
                job_timeout=7200,
            )
        except Exception as exc:
            await session.rollback()
            paper = await session.get(Paper, paper_id)
            if paper is not None:
                paper.parse_status = "failed"
                paper.parse_error = str(exc)[:2000]
                await session.commit()
            await tasks.update(
                task_id,
                status="failed",
                stage="failed",
                progress=0,
                message="论文处理失败",
                error=str(exc)[:4000],
            )
            raise
