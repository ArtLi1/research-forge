import json
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, not_found
from app.models import (
    Evidence,
    MetadataDefinition,
    Paper,
    PaperChunk,
    ProjectPaper,
)
from app.providers.chat import OpenAICompatibleChatProvider, load_prompt
from app.rag.knowledge import normalize_text
from app.schemas.knowledge import (
    MetadataAutoFillResult,
    MetadataDefinitionCreate,
    MetadataDefinitionUpdate,
    PaperMetadataUpdate,
)
from app.services.knowledge import KnowledgeService
from app.services.papers import normalize_title


def validate_metadata_value(definition: MetadataDefinition, value: Any) -> Any:
    if value is None:
        return None
    if definition.value_type == "text" and isinstance(value, str):
        return value
    if definition.value_type == "boolean" and isinstance(value, bool):
        return value
    if definition.value_type == "single_enum" and isinstance(value, str):
        if value in (definition.options or []):
            return value
    if definition.value_type == "multi_enum" and isinstance(value, list):
        if all(isinstance(item, str) and item in (definition.options or []) for item in value):
            return value
    if definition.value_type == "rating" and type(value) in {int, float}:
        if 1 <= value <= 5:
            return value
    raise AppError(
        "INVALID_METADATA_VALUE",
        "元数据值与字段定义不匹配",
        details={
            "definition_id": str(definition.id),
            "value_type": definition.value_type,
        },
    )


class MetadataService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[MetadataDefinition]:
        return list(
            await self.session.scalars(
                select(MetadataDefinition).order_by(MetadataDefinition.created_at)
            )
        )

    async def get(self, definition_id: uuid.UUID) -> MetadataDefinition:
        definition = await self.session.get(MetadataDefinition, definition_id)
        if definition is None:
            raise not_found("metadata_definition", definition_id)
        return definition

    async def _locked_definition(self, definition_id: uuid.UUID) -> MetadataDefinition:
        definition = await self.session.scalar(
            select(MetadataDefinition)
            .where(MetadataDefinition.id == definition_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if definition is None:
            raise not_found("metadata_definition", definition_id)
        return definition

    @staticmethod
    def _definition_snapshot(definition: MetadataDefinition) -> tuple[Any, ...]:
        return (
            definition.name,
            definition.description,
            definition.value_type,
            tuple(definition.options or []),
            definition.auto_extract,
            definition.scope,
        )

    async def create(self, data: MetadataDefinitionCreate) -> MetadataDefinition:
        definition = MetadataDefinition(**data.model_dump())
        self.session.add(definition)
        await self.session.commit()
        await self.session.refresh(definition)
        return definition

    async def update(
        self, definition_id: uuid.UUID, data: MetadataDefinitionUpdate
    ) -> MetadataDefinition:
        definition = await self._locked_definition(definition_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(definition, key, value)
        if definition.value_type in {"single_enum", "multi_enum"} and not definition.options:
            raise AppError("INVALID_METADATA_VALUE", "枚举字段必须保留至少一个选项")
        await self.session.commit()
        await self.session.refresh(definition)
        return definition

    async def delete(self, definition_id: uuid.UUID) -> None:
        definition = await self._locked_definition(definition_id)
        key = str(definition.id)
        if definition.scope == "global_paper":
            papers = list(await self.session.scalars(select(Paper)))
            for paper in papers:
                values = dict(paper.global_metadata)
                values.pop(key, None)
                paper.global_metadata = values
        else:
            project_papers = list(await self.session.scalars(select(ProjectPaper)))
            for project_paper in project_papers:
                values = dict(project_paper.project_metadata)
                values.pop(key, None)
                project_paper.project_metadata = values
        await self.session.execute(
            delete(Evidence).where(
                Evidence.target_type == "metadata_value",
                Evidence.target_id == definition.id,
            )
        )
        await self.session.delete(definition)
        await self.session.commit()

    async def update_paper_metadata(self, paper_id: uuid.UUID, data: PaperMetadataUpdate) -> Paper:
        paper = await self.session.scalar(
            select(Paper)
            .where(Paper.id == paper_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if paper is None:
            raise not_found("paper", paper_id)
        fixed = data.model_dump(exclude_unset=True, exclude={"custom_values"}, mode="python")
        for key, value in fixed.items():
            setattr(paper, key, value)
        if "title" in fixed:
            paper.normalized_title = normalize_title(paper.title)
        values = dict(paper.global_metadata)
        for definition_id, value in data.custom_values.items():
            definition = await self.get(definition_id)
            if definition.scope != "global_paper":
                raise AppError("INVALID_METADATA_VALUE", "该字段不是全局论文元数据")
            values[str(definition.id)] = validate_metadata_value(definition, value)
        paper.global_metadata = values
        await self.session.commit()
        await self.session.refresh(paper)
        return paper

    async def set_value(
        self,
        definition_id: uuid.UUID,
        paper_id: uuid.UUID,
        value: Any,
        project_id: uuid.UUID | None = None,
        *,
        commit: bool = True,
    ) -> Any:
        definition = await self._locked_definition(definition_id)
        checked = validate_metadata_value(definition, value)
        if definition.scope == "global_paper":
            paper = await self.session.scalar(
                select(Paper)
                .where(Paper.id == paper_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if paper is None:
                raise not_found("paper", paper_id)
            values = dict(paper.global_metadata)
            values[str(definition.id)] = checked
            paper.global_metadata = values
        else:
            if project_id is None:
                raise AppError("INVALID_METADATA_VALUE", "项目论文字段必须提供 project_id")
            link = await self.session.scalar(
                select(ProjectPaper)
                .where(ProjectPaper.project_id == project_id, ProjectPaper.paper_id == paper_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if link is None:
                raise not_found("paper", paper_id)
            values = dict(link.project_metadata)
            values[str(definition.id)] = checked
            link.project_metadata = values
        if commit:
            await self.session.commit()
        return checked

    async def auto_fill(
        self,
        definition_id: uuid.UUID,
        paper_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> MetadataAutoFillResult:
        definition = await self.get(definition_id)
        if not definition.auto_extract:
            raise AppError("INVALID_METADATA_VALUE", "该字段未启用 Agent 自动填充")
        knowledge = await KnowledgeService(self.session).get(paper_id)
        expected_definition = self._definition_snapshot(definition)
        evidence_chunks = []
        remaining = get_settings().knowledge_batch_chars
        for source_chunk in await self.session.scalars(
            select(PaperChunk)
            .where(PaperChunk.paper_id == paper_id)
            .order_by(PaperChunk.order_index)
            .limit(24)
        ):
            if remaining <= 0:
                break
            content = source_chunk.content[:remaining]
            evidence_chunks.append(
                {
                    "chunk_id": str(source_chunk.id),
                    "content": content,
                    "page_start": source_chunk.page_start,
                    "page_end": source_chunk.page_end,
                }
            )
            remaining -= len(content)
        provider = OpenAICompatibleChatProvider()
        await self.session.commit()
        result = await provider.generate_structured(
            [
                {"role": "system", "content": load_prompt("extract_metadata_v1.md")},
                {
                    "role": "user",
                    "content": (
                        f"字段名称：{definition.name}\n字段说明：{definition.description}\n"
                        f"类型：{definition.value_type}\n选项：{definition.options}\n"
                        f"论文知识卡：{knowledge.content.model_dump(mode='json')}"
                        f"\n可引用正文块：{json.dumps(evidence_chunks, ensure_ascii=False)}"
                    ),
                },
            ],
            MetadataAutoFillResult,
            temperature=0,
        )
        definition = await self._locked_definition(definition_id)
        current = await KnowledgeService(self.session).get(paper_id)
        if (
            self._definition_snapshot(definition) != expected_definition
            or current.version_id != knowledge.version_id
        ):
            raise AppError(
                "METADATA_CONTEXT_CONFLICT", "字段或知识已变化，请重新提取", status_code=409
            )
        result.value = validate_metadata_value(definition, result.value)
        await self.set_value(definition_id, paper_id, result.value, project_id, commit=False)
        chunk_ids = {ref.chunk_id for ref in result.evidence}
        chunks = {
            row.id: row
            for row in await self.session.scalars(
                select(PaperChunk).where(
                    PaperChunk.id.in_(chunk_ids), PaperChunk.paper_id == paper_id
                )
            )
        }
        accepted_refs = []
        for ref in result.evidence:
            chunk = chunks.get(ref.chunk_id)
            quote = normalize_text(ref.quote)
            if (
                chunk
                and quote
                and quote in normalize_text(chunk.content)
                and (ref.page is None or chunk.page_start <= ref.page <= chunk.page_end)
            ):
                accepted_refs.append(ref)
                self.session.add(
                    Evidence(
                        paper_id=paper_id,
                        chunk_id=chunk.id,
                        target_type="metadata_value",
                        target_id=definition_id,
                        field_path=str(definition_id),
                        page=ref.page or chunk.page_start,
                        section=ref.section,
                        quote=ref.quote,
                        source_type="agent_evaluation",
                        confidence=ref.confidence,
                    )
                )
        await self.session.commit()
        result.evidence = accepted_refs
        return result
