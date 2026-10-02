import asyncio
import json
from collections.abc import Awaitable, Callable, Hashable
from datetime import UTC, datetime
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents.state import ResearchState
from app.core.errors import AppError
from app.prompts import get_prompt
from app.providers.chat import ChatModelProvider
from app.rag.retrieval import KnowledgeRetriever
from app.schemas.scheme import CandidateSet, RetrievalPlan
from app.services.scheme_validation import SchemeValidator

Checkpoint = Callable[[ResearchState], Awaitable[None]]


class ResearchWorkflow:
    """Pure research orchestration; no database, queue, or ORM lifecycle."""

    def __init__(
        self,
        chat: ChatModelProvider,
        retriever: KnowledgeRetriever,
        *,
        max_revisions: int = 1,
        top_k: int = 15,
        checkpoint: Checkpoint | None = None,
    ) -> None:
        self.chat, self.retriever = chat, retriever
        self.validator = SchemeValidator(chat)
        self.max_revisions, self.top_k = max_revisions, top_k
        self.checkpoint = checkpoint

    async def run(self, state: ResearchState) -> ResearchState:
        if state.next_step in {"plan", "retrieve"} and (
            not state.scope.paper_ids or not state.scope.knowledge_version_ids
        ):
            raise AppError(
                "INSUFFICIENT_KNOWLEDGE", "项目尚无可检索的知识，请先提取知识卡", status_code=409
            )
        graph = StateGraph(ResearchState)
        nodes = {
            "plan": self.plan,
            "retrieve": self.retrieve,
            "propose": self.propose,
            "evaluate": self.evaluate,
        }
        for name, node in nodes.items():
            graph.add_node(name, node)
        routes: dict[Hashable, str] = {**{name: name for name in nodes}, "done": END}
        graph.add_conditional_edges(START, lambda state: state.next_step, routes)
        for name in nodes:
            graph.add_conditional_edges(name, lambda state: state.next_step, routes)
        result = await graph.compile().ainvoke(
            state,
            config={"recursion_limit": 8 + 2 * self.max_revisions},
        )
        return ResearchState.model_validate(result)

    async def advance(self, state: ResearchState, stage: str, **changes: Any) -> dict[str, Any]:
        updated = ResearchState.model_validate(
            {
                **state.model_dump(),
                **changes,
                "steps": [
                    *state.steps,
                    {
                        "name": stage,
                        "status": "completed",
                        "finished_at": datetime.now(UTC).isoformat(),
                    },
                ],
            }
        )
        if self.checkpoint:
            await self.checkpoint(updated)
        return updated.model_dump()

    async def plan(self, state: ResearchState) -> dict[str, Any]:
        plan = await self.chat.generate_structured(
            [
                {
                    "role": "system",
                    "content": get_prompt(
                        "plan_knowledge_retrieval_v2.md", offloading=True
                    ).content,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": state.goal,
                            "project_context": state.project_context.model_dump(),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            RetrievalPlan,
            temperature=0,
        )
        return await self.advance(
            state, "plan_retrieval", retrieval_plan=plan, next_step="retrieve"
        )

    async def retrieve(self, state: ResearchState) -> dict[str, Any]:
        if state.retrieval_plan is None:
            raise AppError("INVALID_WORKFLOW_STATE", "工作流缺少检索计划", status_code=500)
        scenarios, algorithms = await asyncio.gather(
            self.retriever.retrieve(
                state.scope, state.retrieval_plan.scenario_queries, "scenario", limit=self.top_k
            ),
            self.retriever.retrieve(
                state.scope, state.retrieval_plan.algorithm_queries, "algorithm", limit=self.top_k
            ),
        )
        if not scenarios and not algorithms:
            raise AppError(
                "INSUFFICIENT_KNOWLEDGE", "项目尚无可检索的知识，请先提取知识卡", status_code=409
            )
        return await self.advance(
            state,
            "retrieve_knowledge",
            scenario_knowledge=scenarios,
            algorithm_knowledge=algorithms,
            next_step="propose",
        )

    async def propose(self, state: ResearchState) -> dict[str, Any]:
        if state.rounds > self.max_revisions:
            raise AppError("SCHEME_VALIDATION_FAILED", "候选方案达到最大修正次数", status_code=502)
        result = await self.chat.generate_structured(
            [
                {
                    "role": "system",
                    "content": get_prompt("generate_schemes_v1.md", offloading=True).content,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": state.goal,
                            "project_context": state.project_context.model_dump(),
                            "user_ideas": [item.model_dump(mode="json") for item in state.ideas],
                            "scenario_inspirations": [
                                item.model_dump(mode="json") for item in state.scenario_knowledge
                            ],
                            "algorithm_inspirations": [
                                item.model_dump(mode="json") for item in state.algorithm_knowledge
                            ],
                            "validation_feedback": state.validation.feedback
                            if state.validation
                            else [],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            CandidateSet,
            temperature=0.4,
        )
        return await self.advance(
            state,
            "generate_candidates",
            candidates=result.candidates,
            rounds=state.rounds + 1,
            next_step="evaluate",
        )

    async def evaluate(self, state: ResearchState) -> dict[str, Any]:
        result = await self.validator.validate(
            candidates=state.candidates,
            goal=state.goal,
            project_context=state.project_context.model_dump(mode="json"),
        )
        changes = await self.advance(
            state,
            "validate_candidates",
            validation=result,
            next_step="done" if result.passed else "propose",
        )
        if not result.passed and state.rounds > self.max_revisions:
            raise AppError(
                "SCHEME_VALIDATION_FAILED",
                "候选方案在最大修正次数后仍未通过验证",
                status_code=502,
                details={"feedback": result.feedback},
            )
        return changes
