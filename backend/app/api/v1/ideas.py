import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import UserIdea
from app.schemas.project_knowledge import UserIdeaCreate, UserIdeaRead, UserIdeaUpdate
from app.services.ideas import IdeaService

router = APIRouter(tags=["ideas"])


@router.get("/projects/{project_id}/ideas", response_model=list[UserIdeaRead])
async def list_ideas(
    project_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[UserIdea]:
    return await IdeaService(session).list(project_id)


@router.post(
    "/projects/{project_id}/ideas",
    response_model=UserIdeaRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_idea(
    project_id: uuid.UUID,
    data: UserIdeaCreate,
    session: AsyncSession = Depends(get_session),
) -> UserIdea:
    return await IdeaService(session).create(project_id, data)


@router.get("/ideas/{idea_id}", response_model=UserIdeaRead)
async def get_idea(idea_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> UserIdea:
    return await IdeaService(session).get(idea_id)


@router.patch("/ideas/{idea_id}", response_model=UserIdeaRead)
async def update_idea(
    idea_id: uuid.UUID,
    data: UserIdeaUpdate,
    session: AsyncSession = Depends(get_session),
) -> UserIdea:
    return await IdeaService(session).update(idea_id, data)


@router.delete("/ideas/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_idea(idea_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> Response:
    await IdeaService(session).delete(idea_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ideas/{idea_id}/evaluate", response_model=UserIdeaRead)
async def evaluate_idea(
    idea_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> UserIdea:
    return await IdeaService(session).evaluate(idea_id)
