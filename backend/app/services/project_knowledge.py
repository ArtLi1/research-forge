import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found
from app.models import Project, ProjectKnowledge, ProjectKnowledgeVersion
from app.schemas.project_knowledge import (
    ProjectKnowledgeContent,
    ProjectKnowledgeItem,
    ProjectKnowledgeRead,
)
from app.schemas.scheme import CandidateSchemeContent, SchemeRiskAssessment

SCHEME_FIELDS = (
    "core_research_question",
    "scenario_innovation",
    "model_level_changes",
    "algorithm_innovation",
    "possible_paper_contributions",
    "borrowed_mechanisms",
    "expected_advantages",
    "combination_rationale",
    "required_assumptions",
)


class ProjectKnowledgeService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_current(self, project_id: uuid.UUID) -> list[ProjectKnowledgeRead]:
        rows = await self.session.execute(
            select(ProjectKnowledge, ProjectKnowledgeVersion)
            .join(
                ProjectKnowledgeVersion,
                ProjectKnowledgeVersion.id == ProjectKnowledge.current_version_id,
            )
            .where(ProjectKnowledge.project_id == project_id)
            .order_by(ProjectKnowledge.category)
        )
        return [self._read(row, version) for row, version in rows]

    async def add_adopted_idea(
        self,
        project_id: uuid.UUID,
        idea_id: uuid.UUID,
        statement: str,
        *,
        commit: bool = True,
    ) -> None:
        await self._append(
            project_id,
            "research_opportunities",
            [
                ProjectKnowledgeItem(
                    statement=statement,
                    source_type="user_idea",
                    source_id=idea_id,
                )
            ],
            change_summary=f"加入已采纳用户想法 {idea_id}",
            idea_id=idea_id,
            commit=commit,
        )

    async def add_confirmed_scheme(
        self,
        project_id: uuid.UUID,
        scheme_id: uuid.UUID,
        content: CandidateSchemeContent,
        risk: SchemeRiskAssessment,
        *,
        idea_ids: set[uuid.UUID],
    ) -> None:
        additions = [
            ProjectKnowledgeItem(
                statement=statement,
                source_type="accepted_scheme",
                source_id=scheme_id,
            )
            for field in SCHEME_FIELDS
            for statement in getattr(content, field)
        ]
        remaining_risks = [
            *risk.hard_constraint_violations,
            *risk.compatibility_risks,
            *risk.remaining_risks,
        ]
        additions.extend(
            ProjectKnowledgeItem(
                statement=f"剩余风险：{item}",
                source_type="accepted_scheme",
                source_id=scheme_id,
            )
            for item in dict.fromkeys(remaining_risks)
            if item.strip()
        )
        await self._append(
            project_id,
            "confirmed_schemes",
            additions,
            change_summary=f"确认候选方案 {scheme_id}",
            added_idea_ids=idea_ids,
            commit=False,
        )

    async def _append(
        self,
        project_id: uuid.UUID,
        category: str,
        additions: list[ProjectKnowledgeItem],
        *,
        change_summary: str,
        idea_id: uuid.UUID | None = None,
        added_idea_ids: set[uuid.UUID] | None = None,
        commit: bool = True,
    ) -> None:
        # Lock the parent even when the category does not exist yet.
        project = await self.session.scalar(
            select(Project).where(Project.id == project_id).with_for_update()
        )
        if project is None:
            raise not_found("project", project_id)
        row = await self.session.scalar(
            select(ProjectKnowledge)
            .where(
                ProjectKnowledge.project_id == project_id,
                ProjectKnowledge.category == category,
            )
            .execution_options(populate_existing=True)
        )
        current = ProjectKnowledgeContent()
        source_paper_ids: set[str] = set()
        source_idea_ids: set[str] = set()
        if row is None:
            row = ProjectKnowledge(
                project_id=project_id, category=category, current_version_id=None
            )
            self.session.add(row)
            await self.session.flush()
        elif row.current_version_id:
            version = await self.session.get(ProjectKnowledgeVersion, row.current_version_id)
            if version is not None:
                current = ProjectKnowledgeContent.model_validate(version.content)
                source_paper_ids.update(version.source_paper_ids)
                source_idea_ids.update(version.source_idea_ids)

        known = {
            (" ".join(item.statement.lower().split()), str(item.source_id))
            for item in current.items
        }
        fresh = []
        for item in additions:
            key = (" ".join(item.statement.lower().split()), str(item.source_id))
            if key not in known:
                known.add(key)
                fresh.append(item)
        if not fresh:
            return
        current.items.extend(fresh)
        if idea_id:
            source_idea_ids.add(str(idea_id))
        source_idea_ids.update(str(item) for item in (added_idea_ids or set()))
        current_max = await self.session.scalar(
            select(func.coalesce(func.max(ProjectKnowledgeVersion.version_number), 0)).where(
                ProjectKnowledgeVersion.project_knowledge_id == row.id
            )
        )
        next_version = int(current_max or 0) + 1
        version = ProjectKnowledgeVersion(
            project_knowledge_id=row.id,
            version_number=next_version,
            content=current.model_dump(mode="json"),
            change_summary=change_summary,
            source_paper_ids=sorted(source_paper_ids),
            source_idea_ids=sorted(source_idea_ids),
        )
        self.session.add(version)
        await self.session.flush()
        row.current_version_id = version.id
        if commit:
            await self.session.commit()

    @staticmethod
    def _read(row: ProjectKnowledge, version: ProjectKnowledgeVersion) -> ProjectKnowledgeRead:
        return ProjectKnowledgeRead(
            id=row.id,
            project_id=row.project_id,
            category=row.category,
            version_id=version.id,
            version_number=version.version_number,
            content=ProjectKnowledgeContent.model_validate(version.content),
            change_summary=version.change_summary,
            source_paper_ids=[uuid.UUID(item) for item in version.source_paper_ids],
            source_idea_ids=[uuid.UUID(item) for item in version.source_idea_ids],
            created_at=version.created_at,
        )
