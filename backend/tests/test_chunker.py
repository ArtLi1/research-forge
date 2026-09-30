import pytest

from app.rag.chunker import DomainAwareChunker
from app.schemas.paper import ParsedBlock, ParsedDocument


def test_chunker_preserves_section_and_pages() -> None:
    document = ParsedDocument(
        metadata={},
        warnings=[],
        blocks=[
            ParsedBlock(
                block_type="heading",
                content="System Model",
                page=2,
                order_index=0,
                heading_level=2,
            ),
            ParsedBlock(
                block_type="paragraph",
                content="A UAV provides computation service.",
                page=2,
                order_index=1,
            ),
            ParsedBlock(
                block_type="paragraph",
                content="Tasks may be forwarded over multiple hops.",
                page=3,
                order_index=2,
            ),
        ],
    )
    chunks = DomainAwareChunker(target_tokens=100).chunk(document)
    assert len(chunks) == 1
    assert chunks[0].section_title == "System Model"
    assert chunks[0].page_start == 2
    assert chunks[0].page_end == 3


def test_table_is_kept_as_own_chunk() -> None:
    document = ParsedDocument(
        metadata={},
        warnings=[],
        blocks=[
            ParsedBlock(block_type="paragraph", content="Before table.", page=1, order_index=0),
            ParsedBlock(block_type="table", content="| A | B |\n| 1 | 2 |", page=1, order_index=1),
            ParsedBlock(block_type="paragraph", content="After table.", page=1, order_index=2),
        ],
    )
    chunks = DomainAwareChunker(target_tokens=100).chunk(document)
    assert [chunk.chunk_type for chunk in chunks] == ["paragraph", "table", "paragraph"]


@pytest.mark.parametrize(
    "options",
    [
        {"target_tokens": 0},
        {"max_tokens": 100, "overlap": 100},
        {"overlap": -1},
        {"target_tokens": 1201},
    ],
)
def test_invalid_chunk_limits_are_rejected(options):
    with pytest.raises(ValueError):
        DomainAwareChunker(**options)


def test_long_paragraph_does_not_emit_an_overlap_only_duplicate():
    prefix = "MEC task."  # Small enough to become an overlap in the old implementation.
    document = ParsedDocument(
        metadata={},
        warnings=[],
        blocks=[
            ParsedBlock(block_type="paragraph", content=prefix, page=1, order_index=0),
            ParsedBlock(block_type="paragraph", content="offloading " * 100, page=2, order_index=1),
        ],
    )
    chunks = DomainAwareChunker(target_tokens=20, max_tokens=30, overlap=10).chunk(document)
    assert sum(chunk.content == prefix for chunk in chunks) == 1
    assert all(chunk.token_count <= 30 for chunk in chunks)


def test_overlap_does_not_push_merged_paragraph_over_max_tokens():
    document = ParsedDocument(
        metadata={},
        warnings=[],
        blocks=[
            ParsedBlock(block_type="paragraph", content="edge " * 8, page=1, order_index=0),
            ParsedBlock(block_type="paragraph", content="offloading " * 25, page=2, order_index=1),
        ],
    )
    chunks = DomainAwareChunker(target_tokens=20, max_tokens=30, overlap=10).chunk(document)
    assert all(chunk.token_count <= 30 for chunk in chunks)
    assert any("offloading" in chunk.content for chunk in chunks)
