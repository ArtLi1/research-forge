import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

COMPARISON_DIMENSIONS = (
    "应用场景",
    "算法思路",
    "核心机制",
    "创新差异",
    "适用条件",
)


class CompareRequest(BaseModel):
    paper_ids: list[uuid.UUID] = Field(min_length=2, max_length=5)


class ComparisonEntry(BaseModel):
    paper_id: uuid.UUID
    statement: str


class ComparisonDimension(BaseModel):
    dimension: str
    entries: list[ComparisonEntry]
    conclusion_type: Literal["explicit_difference", "synthesis", "unconfirmed"]
    conclusion: str


class ComparisonResult(BaseModel):
    paper_ids: list[uuid.UUID]
    dimensions: list[ComparisonDimension]
    summary: str

    @model_validator(mode="after")
    def validate_fixed_dimensions(self) -> "ComparisonResult":
        names = [item.dimension for item in self.dimensions]
        if len(names) != len(COMPARISON_DIMENSIONS) or set(names) != set(COMPARISON_DIMENSIONS):
            raise ValueError("比较结果必须完整包含五个固定维度")
        return self
