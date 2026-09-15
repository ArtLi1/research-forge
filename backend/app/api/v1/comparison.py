from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.comparison import CompareRequest, ComparisonResult
from app.services.comparison import ComparisonService

router = APIRouter(tags=["comparison"])


@router.post("/papers/compare", response_model=ComparisonResult)
async def compare_papers(
    data: CompareRequest, session: AsyncSession = Depends(get_session)
) -> ComparisonResult:
    return await ComparisonService(session).compare(data.paper_ids)
