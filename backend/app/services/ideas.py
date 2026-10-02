import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context import ResearchContextService
from app.core.errors import AppError, not_found
from app.models import Project, UserIdea
from app.providers.chat import OpenAICompatibleChatProvider, load_prompt
from app.rag.retrieval import KnowledgeRetriever
from app.schemas.project_knowledge import IdeaEvaluation, UserIdeaCreate, UserIdeaUpdate
from app.services.project_knowledge import ProjectKnowledgeService


class IdeaService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, project_id: uuid.UUID) -> list[UserIdea]:
        if await self.session.get(Project, project_id) is None:
            raise not_found("project", project_id)
        result = await self.session.scalars(
            select(UserIdea)
            .where(UserIdea.project_id == project_id)
            .order_by(UserIdea.updated_at.desc())
        )
        return list(result)

    async def get(self, idea_id: uuid.UUID) -> UserIdea:
        idea = await self.session.get(UserIdea, idea_id)
        if idea is None:
            raise not_found("idea", idea_id)
        return idea

    async def create(self, project_id: uuid.UUID, data: UserIdeaCreate) -> UserIdea:
        if await self.session.get(Project, project_id) is None:
            raise not_found("project", project_id)
        idea = UserIdea(
            project_id=project_id,
            **data.model_dump(mode="json"),
        )
        self.session.add(idea)
        await self.session.flush()
        if idea.status == "adopted":
            await ProjectKnowledgeService(self.session).add_adopted_idea(
                project_id, idea.id, idea.content, commit=False
            )
        await self.session.commit()
        await self.session.refresh(idea)
        return idea

    async def update(self, idea_id: uuid.UUID, data: UserIdeaUpdate) -> UserIdea:
        idea = await self._locked(idea_id)
        old_status = idea.status
        for key, value in data.model_dump(exclude_unset=True, mode="json").items():
            setattr(idea, key, value)
        if old_status != "adopted" and idea.status == "adopted":
            await ProjectKnowledgeService(self.session).add_adopted_idea(
                idea.project_id, idea.id, idea.content, commit=False
            )
        await self.session.commit()
        await self.session.refresh(idea)
        return idea

    async def delete(self, idea_id: uuid.UUID) -> None:
        idea = await self._locked(idea_id)
        await self.session.delete(idea)
        await self.session.commit()

    async def evaluate(self, idea_id: uuid.UUID) -> UserIdea:
        idea = await self.get(idea_id)
        project = await self.session.get(Project, idea.project_id)
        if project is None:
            raise not_found("project", idea.project_id)
        expected_content = idea.content
        state = await ResearchContextService(self.session).load(idea.project_id, idea.content)
        await self.session.commit()
        retriever = KnowledgeRetriever()
        scenarios = await retriever.search(state.scope, idea.content, "scenario", limit=10)
        algorithms = await retriever.search(state.scope, idea.content, "algorithm", limit=10)
        provider = OpenAICompatibleChatProvider()
        evaluation = await provider.generate_structured(
            [
                {
                    "role": "system",
                    "content": load_prompt("evaluate_idea_v1.md", offloading_guidance=True),
                },
                {
                    "role": "user",
                    "content": (
                        f"项目目标：{project.research_goal}\n"
                        f"项目偏好：{project.preferences}\n排除项：{project.exclusions}\n"
                        f"用户想法（不得修改）：{idea.content}\n"
                        f"相关场景知识：{[item.model_dump(mode='json') for item in scenarios]}\n"
                        f"相关算法知识：{[item.model_dump(mode='json') for item in algorithms]}"
                    ),
                },
            ],
            IdeaEvaluation,
            temperature=0,
        )
        idea = await self._locked(idea_id)
        if idea.content != expected_content:
            raise AppError("IDEA_VERSION_CONFLICT", "想法已修改，请重新评估", status_code=409)
        idea.agent_evaluation = evaluation.model_dump(mode="json")
        await self.session.commit()
        await self.session.refresh(idea)
        return idea

    async def _locked(self, idea_id: uuid.UUID) -> UserIdea:
        idea = await self.session.scalar(
            select(UserIdea)
            .where(UserIdea.id == idea_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if idea is None:
            raise not_found("idea", idea_id)
        return idea
