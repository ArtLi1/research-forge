import uuid

import pytest
from pydantic import ValidationError

from app.schemas.paper import SearchRequest


def test_search_top_k_is_bounded() -> None:
    with pytest.raises(ValidationError):
        SearchRequest(query="test", top_k=51)


def test_project_scope_accepts_project_id() -> None:
    project_id = uuid.uuid4()
    request = SearchRequest(query="multi-hop offloading", scope="project", project_id=project_id)
    assert request.project_id == project_id
