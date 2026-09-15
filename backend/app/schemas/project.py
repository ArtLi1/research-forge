import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    research_goal: str | None = None
    preferences: dict[str, Any] = {}
    exclusions: list[str] = []


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    research_goal: str | None = None
    preferences: dict[str, Any] | None = None
    exclusions: list[str] | None = None


class ProjectRead(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ProjectPaperCreate(BaseModel):
    note: str | None = None
    project_metadata: dict[str, Any] = {}
