import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import IdeaContext, ProjectContext, ResearchState
from app.core.errors import AppError, not_found
from app.models import PaperKnowledgeCard, Project, ProjectPaper, UserIdea
from app.rag.retrieval import RetrievalScope
from app.services.project_knowledge import ProjectKnowledgeService


class ResearchContextService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load(
        self,
        project_id: uuid.UUID,
        goal: str,
        selected_ids: list[uuid.UUID] | None = None,
    ) -> ResearchState:
        project = await self.session.get(Project, project_id)
        if project is None:
            raise not_found("project", project_id)
        memory = await ProjectKnowledgeService(self.session).list_current(project_id)
        compact = []
        for item in memory:
            if item.category in {"research_opportunities", "confirmed_schemes"}:
                value = item.model_dump(mode="json")
                value["content"]["items"] = value["content"]["items"][-20:]
                compact.append(value)
        query = select(UserIdea).where(UserIdea.project_id == project_id)
        if selected_ids:
            query = query.where(UserIdea.id.in_(selected_ids))
        else:
            query = (
                query.where(
                    UserIdea.status.in_(
                        [
                            "adopted",
                            "to_verify",
                            "partially_feasible",
                        ]
                    )
                )
                .order_by(UserIdea.updated_at.desc())
                .limit(20)
            )
        ideas = list(await self.session.scalars(query))
        if selected_ids and len(ideas) != len(set(selected_ids)):
            raise AppError("IDEA_NOT_FOUND", "存在不属于当前项目的用户想法", status_code=404)
        rows = await self.session.execute(
            select(ProjectPaper.paper_id, PaperKnowledgeCard.current_version_id)
            .outerjoin(PaperKnowledgeCard, PaperKnowledgeCard.paper_id == ProjectPaper.paper_id)
            .where(ProjectPaper.project_id == project_id)
        )
        papers, versions = [], []
        for paper_id, version_id in rows:
            papers.append(str(paper_id))
            if version_id:
                versions.append(str(version_id))
        return ResearchState(
            goal=goal,
            project_context=ProjectContext(
                name=project.name,
                description=project.description,
                research_goal=project.research_goal,
                preferences=project.preferences,
                exclusions=project.exclusions,
                knowledge=compact,
            ),
            ideas=[
                IdeaContext(id=item.id, title=item.title, content=item.content, status=item.status)
                for item in ideas
            ],
            scope=RetrievalScope(paper_ids=papers, knowledge_version_ids=versions),
        )
