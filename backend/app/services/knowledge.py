import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.models import Evidence, Paper, PaperKnowledgeCard, PaperKnowledgeVersion
from app.schemas.knowledge import KnowledgeCardRead, PaperKnowledgeContent


class KnowledgeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, paper_id: uuid.UUID) -> KnowledgeCardRead:
        row = (
            await self.session.execute(
                select(PaperKnowledgeCard, PaperKnowledgeVersion)
                .join(
                    PaperKnowledgeVersion,
                    PaperKnowledgeVersion.id == PaperKnowledgeCard.current_version_id,
                )
                .where(PaperKnowledgeCard.paper_id == paper_id)
            )
        ).first()
        if row is None:
            raise AppError("KNOWLEDGE_NOT_FOUND", "论文尚无知识卡", status_code=404)
        card, version = row
        return KnowledgeCardRead(
            card_id=card.id,
            paper_id=paper_id,
            version_id=version.id,
            version_number=version.version_number,
            status=card.status,
            validation_status=version.validation_status,
            extraction_model=version.extraction_model,
            prompt_version=version.prompt_version,
            content=PaperKnowledgeContent.model_validate(version.content),
            created_at=version.created_at,
        )

    async def evidence(self, paper_id: uuid.UUID) -> list[Evidence]:
        if await self.session.get(Paper, paper_id) is None:
            raise not_found("paper", paper_id)
        return list(
            await self.session.scalars(
                select(Evidence)
                .where(Evidence.paper_id == paper_id)
                .order_by(Evidence.created_at, Evidence.field_path)
            )
        )

    async def save(
        self,
        paper_id: uuid.UUID,
        version_id: uuid.UUID,
        content: PaperKnowledgeContent,
        *,
        model: str,
        prompt_version: str,
    ) -> None:
        if (
            await self.session.scalar(select(Paper).where(Paper.id == paper_id).with_for_update())
            is None
        ):
            raise not_found("paper", paper_id)
        card = await self.session.scalar(
            select(PaperKnowledgeCard)
            .where(PaperKnowledgeCard.paper_id == paper_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if card is None:
            card = PaperKnowledgeCard(id=uuid.uuid4(), paper_id=paper_id, status="generated")
            self.session.add(card)
            await self.session.flush()
        number = await self.session.scalar(
            select(func.coalesce(func.max(PaperKnowledgeVersion.version_number), 0)).where(
                PaperKnowledgeVersion.card_id == card.id
            )
        )
        self.session.add(
            PaperKnowledgeVersion(
                id=version_id,
                card_id=card.id,
                version_number=int(number or 0) + 1,
                content=content.model_dump(mode="json"),
                extraction_model=model,
                prompt_version=prompt_version,
                validation_status="passed",
            )
        )
        card.current_version_id, card.status = version_id, "generated"
