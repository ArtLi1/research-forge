import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import BackgroundTask, Evidence, Paper
from app.schemas.knowledge import EvidenceRead, KnowledgeCardRead, PaperMetadataUpdate
from app.schemas.paper import PaperRead, PaperUploadResult
from app.schemas.task import TaskRead
from app.services.knowledge import KnowledgeService
from app.services.metadata import MetadataService
from app.services.papers import PaperService

router = APIRouter(prefix="/papers", tags=["papers"])


@router.post(
    "/upload",
    response_model=list[PaperUploadResult],
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_papers(
    files: Annotated[list[UploadFile], File()],
    project_id: Annotated[uuid.UUID | None, Form()] = None,
    session: AsyncSession = Depends(get_session),
) -> list[PaperUploadResult]:
    return await PaperService(session).upload(files, project_id)


@router.get("", response_model=list[PaperRead])
async def list_papers(
    knowledge_ready: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[Paper]:
    return await PaperService(session).list_all(knowledge_ready=knowledge_ready)


@router.get("/{paper_id}", response_model=PaperRead)
async def get_paper(paper_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Paper:
    return await PaperService(session).get(paper_id)


@router.post("/{paper_id}/reparse", response_model=TaskRead, status_code=202)
async def reparse_paper(
    paper_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> BackgroundTask:
    return await PaperService(session).reparse(paper_id)


@router.post("/{paper_id}/extract", response_model=TaskRead, status_code=202)
async def extract_paper_knowledge(
    paper_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> BackgroundTask:
    return await PaperService(session).extract(paper_id)


@router.get("/{paper_id}/knowledge", response_model=KnowledgeCardRead)
async def get_paper_knowledge(
    paper_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> KnowledgeCardRead:
    return await KnowledgeService(session).get(paper_id)


@router.get("/{paper_id}/evidence", response_model=list[EvidenceRead])
async def get_paper_evidence(
    paper_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[Evidence]:
    return await KnowledgeService(session).evidence(paper_id)


@router.patch("/{paper_id}/metadata", response_model=PaperRead)
async def update_paper_metadata(
    paper_id: uuid.UUID,
    data: PaperMetadataUpdate,
    session: AsyncSession = Depends(get_session),
) -> Paper:
    return await MetadataService(session).update_paper_metadata(paper_id, data)
