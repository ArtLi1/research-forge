import uuid
from typing import Any

from app.models import BackgroundTask, Paper, Project, ProjectPaper
from app.schemas.knowledge import AlgorithmKnowledge, PaperKnowledgeContent, ScenarioKnowledge
from app.schemas.scheme import (
    CandidateConstraintCheck,
    CandidateConstraintSet,
    CandidateSchemeContent,
    CandidateSet,
)


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


def diverse_candidates():
    return CandidateSet(
        candidates=[
            candidate("分布式", "分布式博弈"),
            candidate("分层", "分层强化学习"),
            candidate("预测式", "预测式启发算法"),
        ]
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

    async def generate_structured(self, messages, response_model, **_):
        self.messages.append(messages)
        value = next(self.responses)
        if isinstance(value, Exception):
            raise value
        assert isinstance(value, response_model)
        return value


class MemoryVectors:
    """Replace external Chroma only; exercise real workflow, SQL and HTTP contracts."""

    def __init__(self):
        self.chunks, self.knowledge = {}, {}

    async def paper_vector_ids(self, paper_id, *, knowledge=False):
        rows = self.knowledge if knowledge else self.chunks
        return [key for key, (_, metadata) in rows.items() if metadata["paper_id"] == paper_id]

    async def delete_vectors(self, ids, *, knowledge=False):
        rows = self.knowledge if knowledge else self.chunks
        for key in ids:
            rows.pop(key, None)

    async def index_chunks(self, *, ids, documents, metadatas):
        self.chunks.update(
            {key: (doc, meta) for key, doc, meta in zip(ids, documents, metadatas, strict=True)}
        )

    async def index_knowledge(self, *, paper_id, ids, documents, metadatas, replace):
        assert replace is False
        self.knowledge.update(
            {key: (doc, meta) for key, doc, meta in zip(ids, documents, metadatas, strict=True)}
        )

    async def search_knowledge(
        self, query, allowed_paper_ids, top_k=8, knowledge_type=None, *, version_ids=None
    ):
        rows = {
            key: (doc, meta)
            for key, (doc, meta) in self.knowledge.items()
            if meta["paper_id"] in allowed_paper_ids
            and (not knowledge_type or meta["knowledge_type"] == knowledge_type)
            and (version_ids is None or meta["knowledge_version_id"] in version_ids)
        }
        return self.result(rows, top_k)

    async def search_chunks(self, query, allowed_paper_ids, top_k, chunk_types):
        rows = {
            key: (doc, meta)
            for key, (doc, meta) in self.chunks.items()
            if meta["paper_id"] in allowed_paper_ids
            and (not chunk_types or meta["chunk_type"] in chunk_types)
        }
        return self.result(rows, top_k)

    @staticmethod
    def result(rows, limit):
        keys = list(rows)[:limit]
        return {
            "ids": [keys],
            "documents": [[rows[key][0] for key in keys]],
            "metadatas": [[rows[key][1] for key in keys]],
            "distances": [[0.1] * len(keys)],
        }


def knowledge():
    return PaperKnowledgeContent(
        scenarios=[
            ScenarioKnowledge(
                name="Mobile edge computation",
                description="Devices offload tasks to edge servers",
                key_challenge="Deadline and energy constraints",
            )
        ],
        algorithms=[
            AlgorithmKnowledge(
                name="DAG scheduler",
                core_idea="Schedule dependent tasks",
                key_mechanism="Queue-aware scheduling",
                innovation_point="Resource coordination",
            )
        ],
    )


async def research_task(database, store):
    async with database.transaction() as session:
        project = Project(name="恢复测试", exclusions=["不得使用云端执行"])
        session.add(project)
        await session.flush()
        paper = Paper(title="MEC", normalized_title="mec", file_path="test.pdf", file_hash="1")
        session.add(paper)
        await session.flush()
        session.add(ProjectPaper(project_id=project.id, paper_id=paper.id))
        from app.services.knowledge import KnowledgeService

        version_id = uuid.uuid4()
        await KnowledgeService(session).save(
            paper.id, version_id, knowledge(), model="fake", prompt_version="v1"
        )
        from app.rag.knowledge import stage_knowledge

        await stage_knowledge(store, paper.id, version_id, knowledge())
        task = BackgroundTask(
            task_type="scheme_generate",
            resource_type="project",
            resource_id=project.id,
            dispatch_count=1,
            payload={"goal": "降低 DAG 卸载时延"},
        )
        session.add(task)
    return task
