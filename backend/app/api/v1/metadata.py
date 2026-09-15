import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import MetadataDefinition
from app.schemas.knowledge import (
    MetadataAutoFillResult,
    MetadataDefinitionCreate,
    MetadataDefinitionRead,
    MetadataDefinitionUpdate,
    MetadataValueUpdate,
)
from app.services.metadata import MetadataService

router = APIRouter(tags=["metadata"])


@router.get("/metadata-definitions", response_model=list[MetadataDefinitionRead])
async def list_definitions(
    session: AsyncSession = Depends(get_session),
) -> list[MetadataDefinition]:
    return await MetadataService(session).list()


@router.post(
    "/metadata-definitions",
    response_model=MetadataDefinitionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_definition(
    data: MetadataDefinitionCreate,
    session: AsyncSession = Depends(get_session),
) -> MetadataDefinition:
    return await MetadataService(session).create(data)


@router.patch(
    "/metadata-definitions/{definition_id}",
    response_model=MetadataDefinitionRead,
)
async def update_definition(
    definition_id: uuid.UUID,
    data: MetadataDefinitionUpdate,
    session: AsyncSession = Depends(get_session),
) -> MetadataDefinition:
    return await MetadataService(session).update(definition_id, data)


@router.delete(
    "/metadata-definitions/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_definition(
    definition_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    await MetadataService(session).delete(definition_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/papers/{paper_id}/metadata/{definition_id}")
async def set_global_value(
    paper_id: uuid.UUID,
    definition_id: uuid.UUID,
    data: MetadataValueUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    value = await MetadataService(session).set_value(definition_id, paper_id, data.value)
    return {"value": value}


@router.put("/projects/{project_id}/papers/{paper_id}/metadata/{definition_id}")
async def set_project_value(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    definition_id: uuid.UUID,
    data: MetadataValueUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    value = await MetadataService(session).set_value(
        definition_id, paper_id, data.value, project_id
    )
    return {"value": value}


@router.post(
    "/papers/{paper_id}/metadata/{definition_id}/auto-fill",
    response_model=MetadataAutoFillResult,
)
async def auto_fill_global(
    paper_id: uuid.UUID,
    definition_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> MetadataAutoFillResult:
    return await MetadataService(session).auto_fill(definition_id, paper_id)


@router.post(
    "/projects/{project_id}/papers/{paper_id}/metadata/{definition_id}/auto-fill",
    response_model=MetadataAutoFillResult,
)
async def auto_fill_project(
    project_id: uuid.UUID,
    paper_id: uuid.UUID,
    definition_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> MetadataAutoFillResult:
    return await MetadataService(session).auto_fill(definition_id, paper_id, project_id)
