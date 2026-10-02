import re
import uuid
from pathlib import Path

import structlog
from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.models import BackgroundTask, Paper, Project, ProjectPaper
from app.providers.storage import LocalPaperStorage
from app.repositories.papers import PaperRepository
from app.schemas.paper import PaperUploadResult
from app.services.tasks import TaskService

logger = structlog.get_logger()


def normalize_title(title: str) -> str:
    cleaned = re.sub(r"[^\w\s]", " ", title.lower(), flags=re.UNICODE)
    return " ".join(cleaned.split())


class PaperService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PaperRepository(session)
        self.storage = LocalPaperStorage()

    async def list_all(self, *, knowledge_ready: bool = False) -> list[Paper]:
        return await self.repo.list_all(knowledge_ready=knowledge_ready)

    async def get(self, paper_id: uuid.UUID) -> Paper:
        paper = await self.repo.get(paper_id)
        if paper is None:
            raise not_found("paper", paper_id)
        return paper

    async def upload(
        self, files: list[UploadFile], project_id: uuid.UUID | None
    ) -> list[PaperUploadResult]:
        settings = get_settings()
        if not files or len(files) > settings.max_upload_files:
            raise AppError(
                "UNSUPPORTED_PDF",
                f"每批需上传 1 至 {settings.max_upload_files} 个 PDF",
                status_code=400,
            )
        if project_id is not None and await self.session.get(Project, project_id) is None:
            raise not_found("project", project_id)
        await self.session.commit()

        results: list[PaperUploadResult] = []
        for upload in files:
            results.append(await self._upload_one(upload, project_id))
        return results

    async def _upload_one(
        self, upload: UploadFile, project_id: uuid.UUID | None
    ) -> PaperUploadResult:
        paper_id = uuid.uuid4()
        path, file_hash = await self.storage.save(upload, paper_id)
        existing = await self.repo.by_hash(file_hash)
        if existing is not None:
            self.storage.delete(path)
            if project_id is not None:
                await self._associate_if_missing(project_id, existing.id)
                await self.session.commit()
            return PaperUploadResult(paper=existing, task_id=None, duplicate=True)

        title = (Path(upload.filename or "untitled.pdf").stem.strip() or "Untitled")[:1000]
        paper = Paper(
            id=paper_id,
            title=title,
            normalized_title=normalize_title(title),
            authors=[],
            keywords=[],
            file_path=str(path),
            file_hash=file_hash,
            source_type="upload",
            parse_status="queued",
            global_metadata={},
        )
        task = BackgroundTask(
            task_type="paper_parse",
            resource_type="paper",
            resource_id=paper.id,
            active_key=f"paper:{paper.id}",
        )
        try:
            await self.repo.add(paper)
            self.session.add(task)
            await self.session.flush()
            if project_id is not None:
                await self._associate_if_missing(project_id, paper.id)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            self.storage.delete(path)
            existing = await self.repo.by_hash(file_hash)
            if existing is None:
                raise
            if project_id is not None:
                await self._associate_if_missing(project_id, existing.id)
                await self.session.commit()
            return PaperUploadResult(paper=existing, task_id=None, duplicate=True)
        except BaseException:
            await self.session.rollback()
            # Commit acknowledgement can be lost after PostgreSQL has committed.
            # Preserve a file unless the database confirms it has no owner.
            try:
                if await self.session.get(Paper, paper_id) is None:
                    self.storage.delete(path)
            except Exception:
                logger.exception("upload_persistence_uncertain", paper_id=str(paper_id))
            raise
        await self.session.refresh(paper)
        await TaskService(self.session).dispatch(task.id)
        return PaperUploadResult(paper=paper, task_id=task.id, duplicate=False)

    async def reparse(self, paper_id: uuid.UUID) -> BackgroundTask:
        paper = await self.get(paper_id)
        paper.parse_status = "queued"
        paper.parse_error = None
        task = BackgroundTask(
            task_type="paper_parse",
            resource_type="paper",
            resource_id=paper.id,
            active_key=f"paper:{paper.id}",
        )
        self.session.add(task)
        await self._commit_task()
        await TaskService(self.session).dispatch(task.id)
        return task

    async def extract(self, paper_id: uuid.UUID) -> BackgroundTask:
        paper = await self.get(paper_id)
        if paper.parse_status not in {"completed", "partial"}:
            raise AppError(
                "KNOWLEDGE_EXTRACTION_FAILED",
                "论文正文尚未完成解析",
                status_code=409,
            )
        task = BackgroundTask(
            task_type="knowledge_extract",
            resource_type="paper",
            resource_id=paper.id,
            active_key=f"paper:{paper.id}",
        )
        self.session.add(task)
        await self._commit_task()
        await TaskService(self.session).dispatch(task.id)
        return task

    async def _associate_if_missing(self, project_id: uuid.UUID, paper_id: uuid.UUID) -> None:
        key = {"project_id": project_id, "paper_id": paper_id}
        if await self.session.get(ProjectPaper, key) is None:
            self.session.add(
                ProjectPaper(
                    project_id=project_id,
                    paper_id=paper_id,
                    project_metadata={},
                )
            )

    async def _commit_task(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("PAPER_TASK_ACTIVE", "该论文已有任务正在处理", status_code=409) from exc
