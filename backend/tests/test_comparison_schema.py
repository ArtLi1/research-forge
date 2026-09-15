import uuid

import pytest
from pydantic import ValidationError

from app.schemas.comparison import (
    COMPARISON_DIMENSIONS,
    ComparisonDimension,
    ComparisonResult,
)


def test_comparison_requires_all_fixed_dimensions() -> None:
    paper_ids = [uuid.uuid4(), uuid.uuid4()]
    result = ComparisonResult(
        paper_ids=paper_ids,
        dimensions=[
            ComparisonDimension(
                dimension=name,
                entries=[],
                conclusion_type="unconfirmed",
                conclusion="证据不足",
            )
            for name in COMPARISON_DIMENSIONS
        ],
        summary="五维比较",
    )
    assert len(result.dimensions) == 5


def test_comparison_rejects_incomplete_dimensions() -> None:
    with pytest.raises(ValidationError, match="五个固定维度"):
        ComparisonResult(
            paper_ids=[uuid.uuid4(), uuid.uuid4()],
            dimensions=[],
            summary="invalid",
        )
