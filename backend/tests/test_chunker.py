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
