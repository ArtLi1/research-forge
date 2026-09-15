from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.paper import EvidencePack, SearchRequest
from app.services.search import SearchService

router = APIRouter(tags=["search"])


@router.post("/search", response_model=EvidencePack)
async def search(
    request: SearchRequest, session: AsyncSession = Depends(get_session)
) -> EvidencePack:
    return await SearchService(session).search(request)
