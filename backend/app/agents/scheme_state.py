import uuid
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class ProjectAgentContext(BaseModel):
    name: str
    description: str
    research_goal: str | None
    preferences: dict[str, Any]
    exclusions: list[str]
    knowledge: list[dict[str, Any]] = Field(default_factory=list)


class UserIdeaContext(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    status: str
    source_type: str = "user_idea"


class RetrievedKnowledgeItem(BaseModel):
    id: str
    paper_id: uuid.UUID
    knowledge_type: Literal["scenario", "algorithm"]
    name: str
    content: str
    score: float


class SchemeAgentState(TypedDict, total=False):
    project_id: str
    agent_run_id: str
    thread_id: str
    goal: str
    selected_idea_ids: list[str]
    project_context: dict[str, Any]
    ideas: list[dict[str, Any]]
    retrieval_plan: dict[str, list[str]]
    scenario_knowledge: list[dict[str, Any]]
    algorithm_knowledge: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    validation: dict[str, Any]
    validation_feedback: list[str]
    risks: list[dict[str, Any]]
    retry_count: int
    candidate_ids: list[str]
    steps: list[dict[str, Any]]
