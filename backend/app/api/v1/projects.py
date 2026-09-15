import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Paper, Project
from app.schemas.paper import PaperRead
from app.schemas.project import ProjectCreate, ProjectPaperCreate, ProjectRead, ProjectUpdate
from app.schemas.project_knowledge import ProjectKnowledgeRead
from app.services.project_knowledge import ProjectKnowledgeService
from app.services.projects import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[Project]:
    return await ProjectService(session).list_all()


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate, session: AsyncSession = Depends(get_session)
) -> Project:
    return await ProjectService(session).create(data)


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> Project:
    return await ProjectService(session).get(project_id)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
) -> Project:
    return await ProjectService(session).update(project_id, data)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> Response:
    await ProjectService(session).delete(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/papers", response_model=list[PaperRead])
async def list_project_papers(
    project_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[Paper]:
    return await ProjectService(session).list_papers(project_id)


@router.post(
    "/{project_id}/papers/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def add_project_paper(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    data: ProjectPaperCreate | None = None,
    session: AsyncSession = Depends(get_session),
) -> Response:
    await ProjectService(session).add_paper(project_id, paper_id, data or ProjectPaperCreate())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{project_id}/papers/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_project_paper(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    await ProjectService(session).remove_paper(project_id, paper_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/knowledge", response_model=list[ProjectKnowledgeRead])
async def get_project_knowledge(
    project_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[ProjectKnowledgeRead]:
    await ProjectService(session).get(project_id)
    return await ProjectKnowledgeService(session).list_current(project_id)
