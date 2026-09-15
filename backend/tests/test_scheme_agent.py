import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.agents.scheme_agent import MAX_GENERATION_RETRIES, SchemeAgent
from app.agents.scheme_state import ProjectAgentContext, RetrievedKnowledgeItem
from app.agents.scheme_tools import KnowledgeSearchTool, SchemeAgentTools
from app.core.errors import AppError
from app.schemas.scheme import (
    CandidateConstraintCheck,
    CandidateConstraintSet,
    CandidateSchemeContent,
    CandidateSet,
    RetrievalPlan,
    SchemeGenerateRequest,
)
from app.services.scheme_validation import SchemeValidator
from app.services.schemes import SchemeService


def candidate(name: str, route: str) -> CandidateSchemeContent:
    return CandidateSchemeContent(
        name=name,
        core_research_question=[f"{route} 的核心问题"],
        scenario_innovation=[f"{route} 场景"],
        model_level_changes=[f"{route} 模型"],
        algorithm_innovation=[f"{route} 算法"],
        possible_paper_contributions=[],
        borrowed_mechanisms=[],
        expected_advantages=[],
        combination_rationale=[],
        required_assumptions=[],
        simple_combination_risk="低",
        novelty_risk="待验证",
        compatibility_risks=[],
        implementation_complexity="medium",
        recommendation_score=4,
        unresolved_questions=[],
    )


def checks(violation: str | None = None) -> CandidateConstraintSet:
    return CandidateConstraintSet(
        checks=[
            CandidateConstraintCheck(
                candidate_index=index,
                goal_alignment_passed=True,
                compatibility_passed=True,
                hard_constraint_violations=[violation] if violation and index == 0 else [],
            )
            for index in range(3)
        ]
    )


class FakeChatProvider:
    model = "fake-model"

    def __init__(self, responses: list[Any]) -> None:
        self.responses = iter(responses)
        self.messages: list[list[dict[str, str]]] = []

    async def generate_structured(
        self, messages: list[dict[str, str]], response_model: type[Any], **_: Any
    ) -> Any:
        self.messages.append(messages)
        value = next(self.responses)
        assert isinstance(value, response_model)
        return value


class FakeProjectTool:
    async def run(self, _: uuid.UUID) -> ProjectAgentContext:
        return ProjectAgentContext(
            name="项目",
            description="",
            research_goal="降低时延",
            preferences={},
            exclusions=["不得使用云端执行"],
        )


class FakeIdeaTool:
    async def run(self, _: uuid.UUID, selected_idea_ids=None) -> list[Any]:
        return []


class FakeKnowledgeTool:
    async def run(self, project_id, query, knowledge_type, limit=15):
        del project_id, query, limit
        return [
            RetrievedKnowledgeItem(
                id=f"knowledge:{knowledge_type}",
                paper_id=uuid.uuid4(),
                knowledge_type=knowledge_type,
                name=f"{knowledge_type} inspiration",
                content="可迁移的启发知识",
                score=0.9,
            )
        ]


class WorkflowAgent(SchemeAgent):
    async def _progress(self, stage: str, progress: int, message: str) -> None:
        del stage, progress, message

    async def _persist_candidates(self, state):
        return {
            "candidate_ids": [str(uuid.uuid4()) for _ in state["candidates"]],
            "steps": self._step(state, "persist_candidates", candidate_count=3),
        }


def make_agent(chat: FakeChatProvider) -> WorkflowAgent:
    tools = SchemeAgentTools(
        project_context=FakeProjectTool(),  # type: ignore[arg-type]
        knowledge_search=FakeKnowledgeTool(),  # type: ignore[arg-type]
        user_ideas=FakeIdeaTool(),  # type: ignore[arg-type]
    )
    return WorkflowAgent(
        SimpleNamespace(),  # type: ignore[arg-type]
        uuid.uuid4(),
        SchemeGenerateRequest(goal="降低边缘推理时延"),
        uuid.uuid4(),
        chat=chat,  # type: ignore[arg-type]
        tools=tools,
        validator=SchemeValidator(chat),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_agent_feedback_retry_then_succeeds_and_builds_trace() -> None:
    too_similar = CandidateSet(
        candidates=[
            candidate(f"相似方案{index}", "同一种集中式联合优化路线") for index in range(3)
        ]
    )
    diverse = CandidateSet(
        candidates=[
            candidate("分布式方案", "分布式博弈"),
            candidate("分层方案", "分层强化学习"),
            candidate("预测方案", "预测式启发算法"),
        ]
    )
    chat = FakeChatProvider(
        [
            RetrievalPlan(
                scenario_queries=["edge scenario"], algorithm_queries=["latency algorithm"]
            ),
            too_similar,
            checks(),
            diverse,
            checks(),
        ]
    )
    agent = make_agent(chat)
    state = await agent._build_graph().ainvoke(  # noqa: SLF001
        {
            "project_id": str(agent.project_id),
            "agent_run_id": str(uuid.uuid4()),
            "thread_id": agent.thread_id,
            "goal": agent.request.goal,
            "selected_idea_ids": [],
            "retry_count": 0,
            "steps": [],
        },
        config={"configurable": {"thread_id": agent.thread_id}},
    )

    assert state["retry_count"] == 1
    assert len(state["candidate_ids"]) == 3
    assert "结构过于相似" in chat.messages[3][1]["content"]
    trace = agent._trace_output(state)  # noqa: SLF001
    assert trace["retrieved_scenario_count"] == 1
    assert trace["retrieved_algorithm_count"] == 1
    assert trace["validation"] == {
        "diversity": True,
        "goal_alignment": True,
        "constraints": True,
        "compatibility": True,
    }


@pytest.mark.asyncio
async def test_semantic_hard_constraint_failure_produces_feedback() -> None:
    values = [
        candidate("分布式", "博弈"),
        candidate("分层", "强化学习"),
        candidate("预测式", "启发算法"),
    ]
    validator = SchemeValidator(FakeChatProvider([checks("使用了被排除的云端执行")]))  # type: ignore[arg-type]
    result = await validator.validate(
        candidates=values,
        goal="不得使用云端执行",
        project_context={"exclusions": ["云端执行"]},
    )
    assert not result.passed
    assert any("违反硬约束" in item for item in result.feedback)


@pytest.mark.asyncio
async def test_knowledge_tool_scopes_vector_search_and_type_to_project_papers() -> None:
    project_id, paper_id = uuid.uuid4(), uuid.uuid4()

    class Session:
        async def scalars(self, statement):
            del statement
            return [paper_id]

    class VectorStore:
        async def search_knowledge(
            self, query, allowed_paper_ids, top_k=8, knowledge_type=None
        ):
            assert (query, allowed_paper_ids, top_k, knowledge_type) == (
                "latency",
                [str(paper_id)],
                5,
                "algorithm",
            )
            return {
                "ids": [["version:algorithm:0"]],
                "documents": [["降低时延"]],
                "metadatas": [[{
                    "paper_id": str(paper_id),
                    "knowledge_type": "algorithm",
                    "name": "Actor critic",
                }]],
                "distances": [[0.1]],
            }

    tool = KnowledgeSearchTool(Session(), VectorStore())  # type: ignore[arg-type]
    result = await tool.run(project_id, "latency", "algorithm", limit=5)
    assert [item.name for item in result] == ["Actor critic"]
    assert result[0].score == pytest.approx(0.9)


def test_revision_version_conflict_is_preserved() -> None:
    with pytest.raises(AppError, match="版本已变化"):
        SchemeService._check_version(  # noqa: SLF001
            SimpleNamespace(id=uuid.uuid4()),
            uuid.uuid4(),  # type: ignore[arg-type]
        )


def test_retry_limit_is_one() -> None:
    assert MAX_GENERATION_RETRIES == 1
