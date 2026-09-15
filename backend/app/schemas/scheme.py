import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CandidateSchemeContent(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    core_research_question: list[str]
    scenario_innovation: list[str]
    model_level_changes: list[str]
    algorithm_innovation: list[str]
    possible_paper_contributions: list[str]
    borrowed_mechanisms: list[str]
    expected_advantages: list[str]
    combination_rationale: list[str]
    required_assumptions: list[str]
    simple_combination_risk: str
    novelty_risk: str
    compatibility_risks: list[str]
    implementation_complexity: Literal["low", "medium", "high"]
    recommendation_score: int = Field(ge=1, le=5)
    unresolved_questions: list[str]


class CandidateSet(BaseModel):
    candidates: list[CandidateSchemeContent] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def require_distinct_names(self) -> "CandidateSet":
        names = {" ".join(item.name.lower().split()) for item in self.candidates}
        if len(names) != 3:
            raise ValueError("三个候选方案名称必须不同")
        return self


class CandidateConstraintCheck(BaseModel):
    candidate_index: int = Field(ge=0, le=2)
    goal_alignment_passed: bool
    compatibility_passed: bool
    hard_constraint_violations: list[str] = Field(default_factory=list)
    compatibility_risks: list[str] = Field(default_factory=list)


class CandidateConstraintSet(BaseModel):
    checks: list[CandidateConstraintCheck] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def require_all_candidates(self) -> "CandidateConstraintSet":
        if {item.candidate_index for item in self.checks} != {0, 1, 2}:
            raise ValueError("约束检查必须覆盖三个候选方案")
        return self


class RetrievalPlan(BaseModel):
    scenario_queries: list[str] = Field(min_length=1, max_length=3)
    algorithm_queries: list[str] = Field(min_length=1, max_length=3)


class SchemeValidationResult(BaseModel):
    passed: bool
    diversity_passed: bool
    goal_alignment_passed: bool
    constraint_passed: bool
    compatibility_passed: bool
    feedback: list[str] = Field(default_factory=list)
    candidates: list[CandidateSchemeContent]
    constraint_checks: list[CandidateConstraintCheck] = Field(default_factory=list)


class SchemeRiskAssessment(BaseModel):
    diversity_passed: bool
    goal_alignment_passed: bool
    compatibility_passed: bool
    hard_constraint_violations: list[str] = Field(default_factory=list)
    compatibility_risks: list[str] = Field(default_factory=list)
    remaining_risks: list[str] = Field(default_factory=list)


class SchemeGenerateRequest(BaseModel):
    goal: str = Field(min_length=5, max_length=4000)
    selected_idea_ids: list[uuid.UUID] = Field(default_factory=list)
    candidate_count: Literal[3] = 3


class SchemeReviseRequest(BaseModel):
    instruction: str = Field(min_length=5, max_length=4000)
    expected_version_id: uuid.UUID


class SchemeAcceptRequest(BaseModel):
    expected_version_id: uuid.UUID


class SchemeAbandonRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=2000)


class CandidateVersionRead(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    version_number: int
    parent_version_id: uuid.UUID | None
    content: CandidateSchemeContent
    user_instruction: str | None
    risk_assessment: SchemeRiskAssessment
    model: str
    prompt_version: str
    created_at: datetime


class CandidateSchemeSummary(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: str
    current_version_id: uuid.UUID
    langgraph_thread_id: str
    abandoned_reason: str | None
    accepted_at: datetime | None
    current_version: CandidateVersionRead
    created_at: datetime
    updated_at: datetime


class CandidateSchemeDetail(CandidateSchemeSummary):
    versions: list[CandidateVersionRead]


class AgentRunRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    candidate_id: uuid.UUID | None
    thread_id: str
    run_type: str
    status: str
    input: dict[str, Any]
    output: dict[str, Any]
    error: str | None
    model: str
    prompt_version: str
    started_at: datetime
    finished_at: datetime | None


class AgentTraceRead(BaseModel):
    run_id: uuid.UUID
    status: str
    goal: str
    retrieval_plan: dict[str, list[str]] = Field(default_factory=dict)
    retrieved_scenario_count: int = 0
    retrieved_algorithm_count: int = 0
    retrieved_knowledge_ids: list[str] = Field(default_factory=list)
    candidate_count: int = 0
    retry_count: int = 0
    validation: dict[str, bool] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
