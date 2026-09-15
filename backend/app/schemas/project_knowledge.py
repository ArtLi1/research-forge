import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectKnowledgeItem(BaseModel):
    statement: str
    source_type: Literal["paper", "user_idea", "accepted_scheme"]
    source_id: uuid.UUID
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)


class ProjectKnowledgeContent(BaseModel):
    items: list[ProjectKnowledgeItem] = Field(default_factory=list)


class ProjectKnowledgeRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    category: str
    version_id: uuid.UUID
    version_number: int
    content: ProjectKnowledgeContent
    change_summary: str
    source_paper_ids: list[uuid.UUID]
    source_idea_ids: list[uuid.UUID]
    created_at: datetime


class UserIdeaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    idea_type: Literal[
        "scenario", "model", "algorithm", "innovation", "hypothesis", "question", "other"
    ] = "other"
    status: Literal["draft", "to_verify", "partially_feasible", "adopted", "abandoned"] = "draft"
    tags: list[str] = Field(default_factory=list)
    linked_paper_ids: list[uuid.UUID] = Field(default_factory=list)
    linked_evidence_ids: list[uuid.UUID] = Field(default_factory=list)


class UserIdeaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = Field(default=None, min_length=1)
    idea_type: (
        Literal["scenario", "model", "algorithm", "innovation", "hypothesis", "question", "other"]
        | None
    ) = None
    status: Literal["draft", "to_verify", "partially_feasible", "adopted", "abandoned"] | None = (
        None
    )
    tags: list[str] | None = None
    linked_paper_ids: list[uuid.UUID] | None = None
    linked_evidence_ids: list[uuid.UUID] | None = None


class UserIdeaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    content: str
    idea_type: str
    status: str
    tags: list[str]
    linked_paper_ids: list[str]
    linked_evidence_ids: list[str]
    agent_evaluation: dict | None
    created_at: datetime
    updated_at: datetime


class IdeaEvaluation(BaseModel):
    similar_papers: list[uuid.UUID] = Field(default_factory=list)
    feasible_parts: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    constraint_conflicts: list[str] = Field(default_factory=list)
    complexity_assessment: Literal["low", "medium", "high"]
    recommendation: Literal["keep", "revise", "abandon"]
    rationale: str
