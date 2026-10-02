import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.rag.retrieval import KnowledgeItem, RetrievalScope
from app.schemas.scheme import CandidateSchemeContent, RetrievalPlan, SchemeValidationResult


class ProjectContext(BaseModel):
    name: str
    description: str = ""
    research_goal: str | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    exclusions: list[str] = Field(default_factory=list)
    knowledge: list[dict[str, Any]] = Field(default_factory=list)


class IdeaContext(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    status: str
    source_type: Literal["user_idea"] = "user_idea"


class WorkflowStep(BaseModel):
    name: Literal[
        "plan_retrieval", "retrieve_knowledge", "generate_candidates", "validate_candidates"
    ]
    status: Literal["completed"] = "completed"
    finished_at: datetime


class ResearchState(BaseModel):
    goal: str
    project_context: ProjectContext
    ideas: list[IdeaContext] = Field(default_factory=list)
    scope: RetrievalScope
    retrieval_plan: RetrievalPlan | None = None
    scenario_knowledge: list[KnowledgeItem] = Field(default_factory=list)
    algorithm_knowledge: list[KnowledgeItem] = Field(default_factory=list)
    candidates: list[CandidateSchemeContent] = Field(default_factory=list)
    validation: SchemeValidationResult | None = None
    rounds: int = Field(default=0, ge=0)
    next_step: Literal["plan", "retrieve", "propose", "evaluate", "done"] = "plan"
    steps: list[WorkflowStep] = Field(default_factory=list)

    def trace(self, *, candidate_count: int = 0) -> dict[str, Any]:
        validation = self.validation
        return {
            "goal": self.goal,
            "retrieval_plan": self.retrieval_plan.model_dump() if self.retrieval_plan else {},
            "retrieved_scenario_count": len(self.scenario_knowledge),
            "retrieved_algorithm_count": len(self.algorithm_knowledge),
            "retrieved_knowledge_ids": [
                item.id for item in [*self.scenario_knowledge, *self.algorithm_knowledge]
            ],
            "candidate_count": candidate_count,
            "retry_count": max(0, self.rounds - 1),
            "validation": {
                "diversity": bool(validation and validation.diversity_passed),
                "goal_alignment": bool(validation and validation.goal_alignment_passed),
                "constraints": bool(validation and validation.constraint_passed),
                "compatibility": bool(validation and validation.compatibility_passed),
            },
            "steps": [step.model_dump(mode="json") for step in self.steps],
        }
