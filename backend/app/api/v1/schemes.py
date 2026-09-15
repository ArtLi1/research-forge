import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import BackgroundTask
from app.schemas.scheme import (
    AgentTraceRead,
    CandidateSchemeDetail,
    CandidateSchemeSummary,
    SchemeAbandonRequest,
    SchemeAcceptRequest,
    SchemeGenerateRequest,
    SchemeReviseRequest,
)
from app.schemas.task import TaskRead
from app.services.schemes import SchemeService

router = APIRouter(tags=["schemes"])


@router.post(
    "/projects/{project_id}/schemes/generate",
    response_model=TaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_schemes(
    project_id: uuid.UUID,
    data: SchemeGenerateRequest,
    session: AsyncSession = Depends(get_session),
) -> BackgroundTask:
    return await SchemeService(session).start_generation(project_id, data)


@router.get(
    "/projects/{project_id}/schemes",
    response_model=list[CandidateSchemeSummary],
)
async def list_schemes(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[CandidateSchemeSummary]:
    return await SchemeService(session).list(project_id)


@router.get("/schemes/{scheme_id}", response_model=CandidateSchemeDetail)
async def get_scheme(
    scheme_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> CandidateSchemeDetail:
    return await SchemeService(session).get(scheme_id)


@router.get("/schemes/{scheme_id}/agent-run", response_model=AgentTraceRead)
async def get_scheme_agent_run(
    scheme_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AgentTraceRead:
    return await SchemeService(session).get_agent_trace(scheme_id)


@router.post("/schemes/{scheme_id}/revise", response_model=CandidateSchemeDetail)
async def revise_scheme(
    scheme_id: uuid.UUID,
    data: SchemeReviseRequest,
    session: AsyncSession = Depends(get_session),
) -> CandidateSchemeDetail:
    return await SchemeService(session).revise(scheme_id, data)


@router.post("/schemes/{scheme_id}/accept", response_model=CandidateSchemeDetail)
async def accept_scheme(
    scheme_id: uuid.UUID,
    data: SchemeAcceptRequest,
    session: AsyncSession = Depends(get_session),
) -> CandidateSchemeDetail:
    return await SchemeService(session).accept(scheme_id, data)


@router.post("/schemes/{scheme_id}/abandon", response_model=CandidateSchemeDetail)
async def abandon_scheme(
    scheme_id: uuid.UUID,
    data: SchemeAbandonRequest,
    session: AsyncSession = Depends(get_session),
) -> CandidateSchemeDetail:
    return await SchemeService(session).abandon(scheme_id, data)
