import uuid

import pytest

from app.core.errors import AppError
from app.models import MetadataDefinition
from app.services.metadata import validate_metadata_value


def _definition(value_type: str, options: list[str] | None = None) -> MetadataDefinition:
    return MetadataDefinition(
        id=uuid.uuid4(),
        name="field",
        description="",
        scope="global_paper",
        value_type=value_type,
        options=options,
        auto_extract=False,
    )


@pytest.mark.parametrize(
    ("definition", "value"),
    [
        (_definition("text"), "UAV"),
        (_definition("boolean"), True),
        (_definition("single_enum", ["low", "high"]), "high"),
        (_definition("multi_enum", ["UAV", "MEC"]), ["UAV", "MEC"]),
        (_definition("rating"), 5),
    ],
)
def test_validate_metadata_value_accepts_supported_types(
    definition: MetadataDefinition, value: object
) -> None:
    assert validate_metadata_value(definition, value) == value


@pytest.mark.parametrize(
    ("definition", "value"),
    [
        (_definition("boolean"), "true"),
        (_definition("single_enum", ["low", "high"]), "unknown"),
        (_definition("multi_enum", ["UAV"]), ["UAV", "MEC"]),
        (_definition("rating"), 6),
    ],
)
def test_validate_metadata_value_rejects_invalid_values(
    definition: MetadataDefinition, value: object
) -> None:
    with pytest.raises(AppError, match="元数据值与字段定义不匹配"):
        validate_metadata_value(definition, value)
