import uuid
from unittest.mock import AsyncMock

import pytest
from fakes import candidate
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.base import Base
from app.models import CandidateScheme, CandidateVersion, Project, ProjectKnowledgeVersion, UserIdea
from app.schemas.project_knowledge import UserIdeaCreate
from app.schemas.scheme import SchemeRiskAssessment
from app.services.ideas import IdeaService
from app.services.project_knowledge import ProjectKnowledgeService
from app.services.schemes import SchemeService


class AsyncSessionAdapter:
    """Execute real ORM statements against isolated SQLite without extra dependencies."""

    def __init__(self, session):
        self.session = session
        self.statements = []

    def add(self, row):
        self.session.add(row)

    async def get(self, model, key):
        return self.session.get(model, key)

    async def scalar(self, statement):
        self.statements.append(statement)
        return self.session.scalar(statement)

    async def scalars(self, statement):
        self.statements.append(statement)
        return self.session.scalars(statement)

    async def execute(self, statement):
        self.statements.append(statement)
        return self.session.execute(statement)

    async def flush(self):
        self.session.flush()

    async def commit(self):
        self.session.commit()

    async def refresh(self, row):
        self.session.refresh(row)


@pytest.fixture
def local_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            yield AsyncSessionAdapter(session)
    finally:
        engine.dispose()


@pytest.mark.parametrize("broken_version", [False, True])
async def test_scheme_list_batch_query_and_missing_version(local_session, broken_version):
    project = Project(name="MEC", exclusions=[], preferences={})
    local_session.add(project)
    await local_session.flush()
    for index in range(5):
        scheme = CandidateScheme(
            project_id=project.id,
            title=f"方案{index}",
            langgraph_thread_id="thread",
        )
        local_session.add(scheme)
        await local_session.flush()
        version = CandidateVersion(
            candidate_id=scheme.id,
            version_number=1,
            content=candidate(f"方案{index}", "DAG offloading").model_dump(mode="json"),
            risk_assessment=SchemeRiskAssessment(
                diversity_passed=True,
                goal_alignment_passed=True,
                compatibility_passed=True,
            ).model_dump(mode="json"),
            evidence_ids=[],
            model="test",
            prompt_version="test",
        )
        local_session.add(version)
        await local_session.flush()
        scheme.current_version_id = uuid.uuid4() if broken_version else version.id
    await local_session.commit()
    service = SchemeService(local_session)
    if broken_version:
        with pytest.raises(AppError) as error:
            await service.list(project.id)
        assert error.value.code == "SCHEME_VERSION_CONFLICT"
    else:
        result = await service.list(project.id)
        assert len(result) == 5
        assert all(item.current_version.version_number == 1 for item in result)
    # Two statements for the list, independent of the number of candidates.
    assert len(local_session.statements) == 2


async def test_project_memory_is_idempotent_and_reads_current_version_with_join(local_session):
    project = Project(name="MEC", exclusions=[], preferences={})
    local_session.add(project)
    await local_session.commit()
    service = ProjectKnowledgeService(local_session)
    idea_id = uuid.uuid4()
    await service.add_adopted_idea(project.id, idea_id, "DAG-aware offloading")
    # SQLite executes the ORM flow; the PostgreSQL compiler verifies the row lock.
    assert "FOR UPDATE" in str(local_session.statements[0].compile(dialect=postgresql.dialect()))
    await service.add_adopted_idea(project.id, idea_id, "DAG-aware offloading")
    assert (
        local_session.session.scalar(select(func.count()).select_from(ProjectKnowledgeVersion)) == 1
    )
    local_session.statements.clear()
    rows = await service.list_current(project.id)
    assert len(local_session.statements) == 1
    assert rows[0].content.items[0].statement == "DAG-aware offloading"
    assert rows[0].source_idea_ids == [idea_id]


async def test_adopted_idea_is_not_committed_if_memory_update_fails(local_session, monkeypatch):
    project = Project(name="MEC", exclusions=[], preferences={})
    local_session.add(project)
    await local_session.commit()
    fail = AsyncMock(side_effect=RuntimeError("memory write failed"))
    monkeypatch.setattr(ProjectKnowledgeService, "add_adopted_idea", fail)
    with pytest.raises(RuntimeError, match="memory write failed"):
        await IdeaService(local_session).create(
            project.id,
            UserIdeaCreate(
                title="依赖感知卸载",
                content="先调度前驱任务",
                idea_type="algorithm",
                status="adopted",
            ),
        )
    local_session.session.rollback()
    assert local_session.session.scalar(select(func.count()).select_from(UserIdea)) == 0
    assert fail.await_args.kwargs["commit"] is False
