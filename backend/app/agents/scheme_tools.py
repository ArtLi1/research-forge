import uuid
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, not_found
from app.models import Project, ProjectPaper, UserIdea
from app.providers.chroma import ChromaVectorStore
from app.services.project_knowledge import ProjectKnowledgeService

from .scheme_state import ProjectAgentContext, RetrievedKnowledgeItem, UserIdeaContext


class KnowledgeVectorStore(Protocol):
    async def search_knowledge(
        self,
        query: str,
        allowed_paper_ids: list[str],
        top_k: int = 8,
        knowledge_type: str | None = None,
    ) -> dict[str, Any]: ...


class ProjectContextTool:
    def __init__(self, session: AsyncSession, *, items_per_category: int = 20) -> None:
        self.session = session
        self.items_per_category = items_per_category

    async def run(self, project_id: uuid.UUID) -> ProjectAgentContext:
        project = await self.session.get(Project, project_id)
        if project is None:
            raise not_found("project", project_id)
        knowledge = await ProjectKnowledgeService(self.session).list_current(project_id)
        compact = []
        for item in knowledge:
            if item.category not in {"research_opportunities", "confirmed_schemes"}:
                continue
            data = item.model_dump(mode="json")
            data["content"]["items"] = data["content"]["items"][: self.items_per_category]
            compact.append(data)
        return ProjectAgentContext(
            name=project.name,
            description=project.description,
            research_goal=project.research_goal,
            preferences=project.preferences,
            exclusions=project.exclusions,
            knowledge=compact,
        )


class UserIdeaTool:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(
        self, project_id: uuid.UUID, selected_idea_ids: list[uuid.UUID] | None = None
    ) -> list[UserIdeaContext]:
        selected = selected_idea_ids or []
        statement = select(UserIdea).where(UserIdea.project_id == project_id)
        if selected:
            statement = statement.where(UserIdea.id.in_(selected))
        else:
            statement = (
                statement.where(UserIdea.status.in_(["adopted", "to_verify", "partially_feasible"]))
                .order_by(UserIdea.updated_at.desc())
                .limit(20)
            )
        ideas = list(await self.session.scalars(statement))
        if selected and len(ideas) != len(set(selected)):
            raise AppError("IDEA_NOT_FOUND", "存在不属于当前项目的用户想法", status_code=404)
        return [
            UserIdeaContext(
                id=item.id,
                title=item.title,
                content=item.content,
                status=item.status,
            )
            for item in ideas
        ]


class KnowledgeSearchTool:
    def __init__(
        self, session: AsyncSession, vector_store: KnowledgeVectorStore | None = None
    ) -> None:
        self.session = session
        self.vector_store = vector_store or ChromaVectorStore()
        # This tool lives for one workflow; keep its paper scope stable within that run.
        self._paper_scopes: dict[uuid.UUID, list[str]] = {}

    async def run(
        self,
        project_id: uuid.UUID,
        query: str,
        knowledge_type: Literal["scenario", "algorithm"],
        limit: int = 15,
    ) -> list[RetrievedKnowledgeItem]:
        if project_id not in self._paper_scopes:
            self._paper_scopes[project_id] = [
                str(item)
                for item in await self.session.scalars(
                    select(ProjectPaper.paper_id).where(ProjectPaper.project_id == project_id)
                )
            ]
        paper_ids = self._paper_scopes[project_id]
        if not paper_ids:
            return []
        result = await self.vector_store.search_knowledge(
            query,
            paper_ids,
            top_k=limit,
            knowledge_type=knowledge_type,
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        found: list[RetrievedKnowledgeItem] = []
        for vector_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=True
        ):
            try:
                found.append(
                    RetrievedKnowledgeItem(
                        id=str(vector_id),
                        paper_id=uuid.UUID(str(metadata["paper_id"])),
                        knowledge_type=str(metadata["knowledge_type"]),
                        name=str(metadata["name"]),
                        content=str(document),
                        score=max(0.0, 1.0 - float(distance)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return found[:limit]


@dataclass(slots=True)
class SchemeAgentTools:
    project_context: ProjectContextTool
    knowledge_search: KnowledgeSearchTool
    user_ideas: UserIdeaTool


def build_default_scheme_tools(session: AsyncSession) -> SchemeAgentTools:
    return SchemeAgentTools(
        project_context=ProjectContextTool(session),
        knowledge_search=KnowledgeSearchTool(session),
        user_ideas=UserIdeaTool(session),
    )
