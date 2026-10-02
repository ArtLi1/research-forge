import uuid

import pytest
from fakes import research_task
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Evidence, MetadataDefinition, Paper, PaperChunk
from app.schemas.knowledge import EvidenceRef, MetadataAutoFillResult
from app.services import metadata
from app.services.metadata import MetadataService


async def metadata_context(database, adapters):
    await research_task(database, adapters)
    async with database.transaction() as session:
        paper = await session.scalar(select(Paper))
        chunk = PaperChunk(
            paper_id=paper.id,
            content="Devices use edge servers",
            chunk_type="text",
            page_start=1,
            page_end=1,
            order_index=0,
            token_count=5,
            chroma_id=str(uuid.uuid4()),
        )
        field = MetadataDefinition(
            name="Scenario",
            description="Research scenario",
            scope="global_paper",
            value_type="text",
            auto_extract=True,
        )
        session.add_all([chunk, field])
    return paper.id, field.id, chunk.id


async def test_auto_fill_validates_evidence_and_commits_one_transaction(
    database, adapters, monkeypatch
):
    paper_id, field_id, chunk_id = await metadata_context(database, adapters)

    class Model:
        async def generate_structured(self, messages, response_model, **_):
            assert str(chunk_id) in messages[1]["content"]
            return MetadataAutoFillResult(
                value="MEC",
                evidence=[
                    EvidenceRef(chunk_id=chunk_id, quote="edge servers", page=1, confidence=0.9),
                    EvidenceRef(chunk_id=chunk_id, quote="edge servers", page=999, confidence=0.9),
                    EvidenceRef(chunk_id=uuid.uuid4(), quote="forged source", confidence=0.9),
                    EvidenceRef(chunk_id=chunk_id, quote=" ", confidence=0.9),
                ],
            )

    monkeypatch.setattr(metadata, "OpenAICompatibleChatProvider", Model)
    async with database.sessions() as session:
        result = await MetadataService(session).auto_fill(field_id, paper_id)
        assert len(result.evidence) == 1
        assert await session.scalar(select(func.count()).select_from(Evidence)) == 1
        paper = await session.get(Paper, paper_id)
        assert paper.global_metadata[str(field_id)] == "MEC"


async def test_evidence_failure_does_not_commit_metadata_value(database, adapters, monkeypatch):
    paper_id, field_id, chunk_id = await metadata_context(database, adapters)

    class Model:
        async def generate_structured(self, *_args, **_kwargs):
            return MetadataAutoFillResult(
                value="MEC",
                evidence=[EvidenceRef(chunk_id=chunk_id, quote="edge servers", confidence=0.9)],
            )

    monkeypatch.setattr(metadata, "OpenAICompatibleChatProvider", Model)

    def reject_evidence(session, *_):
        if any(isinstance(value, Evidence) for value in session.new):
            raise RuntimeError("evidence write interrupted")

    event.listen(Session, "before_flush", reject_evidence)
    try:
        async with database.sessions() as session:
            with pytest.raises(RuntimeError, match="evidence write interrupted"):
                await MetadataService(session).auto_fill(field_id, paper_id)
            await session.rollback()
    finally:
        event.remove(Session, "before_flush", reject_evidence)
    async with database.sessions() as session:
        paper = await session.get(Paper, paper_id)
        assert str(field_id) not in paper.global_metadata
        assert await session.scalar(select(func.count()).select_from(Evidence)) == 0


async def test_changed_definition_blocks_stale_model_result(database, adapters, monkeypatch):
    paper_id, field_id, _ = await metadata_context(database, adapters)

    class Model:
        async def generate_structured(self, *_args, **_kwargs):
            async with database.transaction() as session:
                field = await session.get(MetadataDefinition, field_id)
                field.description = "New extraction criteria"
            return MetadataAutoFillResult(value="stale output")

    monkeypatch.setattr(metadata, "OpenAICompatibleChatProvider", Model)
    async with database.sessions() as session:
        with pytest.raises(AppError) as error:
            await MetadataService(session).auto_fill(field_id, paper_id)
        assert error.value.code == "METADATA_CONTEXT_CONFLICT"
        await session.rollback()
