import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceRef(BaseModel):
    chunk_id: uuid.UUID
    page: int | None = None
    section: str | None = None
    quote: str = Field(min_length=1, max_length=1200)
    confidence: float = Field(ge=0, le=1)


class ScenarioKnowledge(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    key_challenge: str = Field(min_length=1)
    innovation_point: str | None = None


class AlgorithmKnowledge(BaseModel):
    name: str = Field(min_length=1)
    core_idea: str = Field(min_length=1)
    key_mechanism: str = Field(min_length=1)
    innovation_point: str = Field(min_length=1)


class PaperKnowledgeContent(BaseModel):
    scenarios: list[ScenarioKnowledge] = Field(default_factory=list)
    algorithms: list[AlgorithmKnowledge] = Field(default_factory=list)


class KnowledgeCardRead(BaseModel):
    card_id: uuid.UUID
    paper_id: uuid.UUID
    version_id: uuid.UUID
    version_number: int
    status: str
    validation_status: str
    extraction_model: str
    prompt_version: str
    content: PaperKnowledgeContent
    created_at: datetime


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    paper_id: uuid.UUID
    chunk_id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    field_path: str
    page: int | None
    section: str | None
    quote: str
    source_type: str
    confidence: float
    created_at: datetime


class MetadataDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    scope: Literal["global_paper", "project_paper"]
    value_type: Literal["text", "boolean", "single_enum", "multi_enum", "rating"]
    options: list[str] | None = None
    auto_extract: bool = False

    @model_validator(mode="after")
    def validate_options(self) -> "MetadataDefinitionCreate":
        enum_type = self.value_type in {"single_enum", "multi_enum"}
        if enum_type and not self.options:
            raise ValueError("枚举字段必须提供 options")
        if not enum_type and self.options:
            raise ValueError("只有枚举字段可以提供 options")
        return self


class MetadataDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    options: list[str] | None = None
    auto_extract: bool | None = None


class MetadataDefinitionRead(MetadataDefinitionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class MetadataValueUpdate(BaseModel):
    value: Any


class MetadataAutoFillResult(BaseModel):
    value: Any = None
    rationale: str = ""
    evidence: list[EvidenceRef] = Field(default_factory=list)


class PaperMetadataUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=1000)
    year: int | None = Field(default=None, ge=1800, le=2200)
    venue: str | None = None
    doi: str | None = None
    abstract: str | None = None
    keywords: list[str] | None = None
    custom_values: dict[uuid.UUID, Any] = Field(default_factory=dict)
