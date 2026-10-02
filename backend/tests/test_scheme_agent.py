import uuid
from types import SimpleNamespace

import pytest
from fakes import FakeChatProvider, candidate, checks, diverse_candidates
from pydantic import ValidationError

from app.agents.state import ProjectContext, ResearchState
from app.agents.workflow import ResearchWorkflow
from app.core.errors import AppError
from app.rag.retrieval import KnowledgeItem, KnowledgeRetriever, RetrievalScope
from app.schemas.scheme import (
    CandidateSet,
    RetrievalPlan,
)
from app.services.scheme_validation import SchemeValidator, schemes_are_diverse
from app.services.schemes import SchemeService


class FakeRetriever:
    async def retrieve(self, scope, queries, kind, *, limit):
        return [
            KnowledgeItem(
                id=f"version:{kind}:0",
                paper_id=uuid.uuid4(),
                knowledge_type=kind,
                name=f"{kind} inspiration",
                content="可迁移知识",
                score=0.9,
            )
        ]


def initial_state():
    return ResearchState(
        goal="降低 DAG 计算卸载时延，不得使用云端执行",
        scope=RetrievalScope(
            paper_ids=[str(uuid.uuid4())], knowledge_version_ids=[str(uuid.uuid4())]
        ),
        project_context=ProjectContext(
            name="项目", research_goal="降低时延", exclusions=["不得使用云端执行"]
        ),
    )


def workflow(chat, **kwargs):
    return ResearchWorkflow(chat, FakeRetriever(), **kwargs)


async def test_agent_feedback_retry_then_succeeds_and_builds_trace():
    similar = CandidateSet(
        candidates=[candidate(str(index), "集中式联合优化") for index in range(3)]
    )
    chat = FakeChatProvider(
        [
            RetrievalPlan(scenario_queries=["MEC"], algorithm_queries=["DAG"]),
            similar,
            checks(),
            diverse_candidates(),
            checks(),
        ]
    )
    result = await workflow(chat).run(initial_state())
    assert result.rounds == 2
    assert result.next_step == "done"
    assert "结构过于相似" in chat.messages[3][1]["content"]
    trace = result.trace(candidate_count=3)
    assert trace["retry_count"] == 1
    assert trace["retrieved_scenario_count"] == trace["retrieved_algorithm_count"] == 1
    assert all(trace["validation"].values())


async def test_resume_uses_last_durable_state_without_replanning():
    snapshots = []

    async def save(state):
        snapshots.append(state.model_dump(mode="json"))

    first = FakeChatProvider(
        [
            RetrievalPlan(scenario_queries=["MEC"], algorithm_queries=["DAG"]),
            RuntimeError("provider interrupted"),
        ]
    )
    with pytest.raises(RuntimeError, match="interrupted"):
        await workflow(first, checkpoint=save).run(initial_state())
    restored = ResearchState.model_validate(snapshots[-1])
    assert restored.next_step == "propose"
    second = FakeChatProvider([diverse_candidates(), checks()])
    completed = await workflow(second).run(restored)
    assert completed.validation.passed
    assert len(second.messages) == 2
    assert [step.name for step in completed.steps].count("plan_retrieval") == 1


async def test_failed_validation_has_bounded_model_calls():
    similar = CandidateSet(candidates=[candidate(str(index), "集中式路线") for index in range(3)])
    chat = FakeChatProvider(
        [
            RetrievalPlan(scenario_queries=["MEC"], algorithm_queries=["DAG"]),
            similar,
            checks(),
            similar,
            checks(),
        ]
    )
    with pytest.raises(AppError) as error:
        await workflow(chat).run(initial_state())
    assert error.value.code == "SCHEME_VALIDATION_FAILED"
    assert len(chat.messages) == 5


async def test_missing_knowledge_fails_before_spending_model_calls():
    state = initial_state().model_copy(update={"scope": RetrievalScope()})
    chat = FakeChatProvider([])
    with pytest.raises(AppError) as error:
        await workflow(chat).run(state)
    assert error.value.code == "INSUFFICIENT_KNOWLEDGE"
    assert chat.messages == []


async def test_semantic_hard_constraint_failure_produces_feedback():
    result = await SchemeValidator(FakeChatProvider([checks("使用了被排除的云端执行")])).validate(
        candidates=diverse_candidates().candidates,
        goal="不得使用云端执行",
        project_context={"exclusions": ["云端执行"]},
    )
    assert not result.passed
    assert any("违反硬约束" in item for item in result.feedback)


async def test_retriever_scopes_papers_versions_and_type():
    paper_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())

    class VectorStore:
        async def search_knowledge(
            self, query, allowed_paper_ids, top_k, knowledge_type, *, version_ids
        ):
            assert (query, allowed_paper_ids, top_k, knowledge_type, version_ids) == (
                "latency",
                [paper_id],
                5,
                "algorithm",
                [version_id],
            )
            return {
                "ids": [["valid", "stale", "foreign"]],
                "documents": [["good"] * 3],
                "metadatas": [
                    [
                        {
                            "paper_id": paper_id,
                            "knowledge_version_id": version_id,
                            "knowledge_type": "algorithm",
                            "name": "Actor critic",
                        },
                        {
                            "paper_id": paper_id,
                            "knowledge_version_id": "old",
                            "knowledge_type": "algorithm",
                        },
                        {
                            "paper_id": str(uuid.uuid4()),
                            "knowledge_version_id": version_id,
                            "knowledge_type": "algorithm",
                        },
                    ]
                ],
                "distances": [[0.1] * 3],
            }

    result = await KnowledgeRetriever(VectorStore()).search(
        RetrievalScope(paper_ids=[paper_id], knowledge_version_ids=[version_id]),
        "latency",
        "algorithm",
        limit=5,
    )
    assert [item.id for item in result] == ["valid"]
    assert result[0].score == pytest.approx(0.9)


def test_revision_version_conflict_is_preserved():
    with pytest.raises(AppError, match="版本已变化"):
        SchemeService._check_version(SimpleNamespace(id=uuid.uuid4()), uuid.uuid4())


def test_different_names_do_not_mask_identical_research_routes():
    assert not schemes_are_diverse([candidate(letter * 450, "DAG offloading") for letter in "ABC"])


def test_retrieval_plan_rejects_blank_queries_and_normalizes_duplicates():
    with pytest.raises(ValidationError):
        RetrievalPlan(scenario_queries=[" "], algorithm_queries=["MEC"])
    plan = RetrievalPlan(scenario_queries=[" MEC ", "MEC"], algorithm_queries=[" DAG offloading "])
    assert plan.scenario_queries == ["MEC"]
    assert plan.algorithm_queries == ["DAG offloading"]


async def test_offloading_goal_and_hard_constraints_reach_all_model_calls():
    chat = FakeChatProvider(
        [
            RetrievalPlan(scenario_queries=["DAG"], algorithm_queries=["queue"]),
            diverse_candidates(),
            checks(),
        ]
    )
    state = initial_state()
    result = await workflow(chat).run(state)
    assert len(result.candidates) == 3
    for messages in chat.messages:
        assert state.goal in messages[1]["content"]
        assert "不得使用云端执行" in messages[1]["content"]
        assert "计算卸载研究的条件性补充规则" in messages[0]["content"]
