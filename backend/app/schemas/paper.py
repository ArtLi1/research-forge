import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PaperRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    authors: list[str]
    year: int | None
    venue: str | None
    doi: str | None
    arxiv_id: str | None
    keywords: list[str]
    source_type: str
    parse_status: str
    parse_error: str | None
    global_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PaperUploadResult(BaseModel):
    paper: PaperRead
    task_id: uuid.UUID | None
    duplicate: bool


class ParsedBlock(BaseModel):
    block_type: Literal["heading", "paragraph", "table", "caption", "formula_context", "reference"]
    content: str
    page: int
    bbox: tuple[float, float, float, float] | None = None
    order_index: int
    heading_level: int | None = None


class ParsedDocument(BaseModel):
    metadata: dict[str, Any]
    blocks: list[ParsedBlock]
    warnings: list[str]


class ChunkData(BaseModel):
    section_title: str | None
    section_level: int | None = None
    chunk_type: str
    content: str
    page_start: int
    page_end: int
    order_index: int
    token_count: int


class SearchFilters(BaseModel):
    year_gte: int | None = None
    year_lte: int | None = None
    paper_ids: list[uuid.UUID] = []
    chunk_types: list[str] = []


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    scope: Literal["global", "project", "papers"] = "global"
    project_id: uuid.UUID | None = None
    filters: SearchFilters = SearchFilters()
    top_k: int = Field(default=12, ge=1, le=50)


class EvidencePackItem(BaseModel):
    paper_id: uuid.UUID
    paper_title: str
    year: int | None
    knowledge_type: str | None = None
    name: str | None = None
    content: str
    section: str | None
    page_start: int | None
    page_end: int | None
    source_type: str = "paper_text"
    score: float


class EvidencePack(BaseModel):
    query: str
    items: list[EvidencePackItem]
    missing_information: list[str] = []
    conflicting_groups: list[list[uuid.UUID]] = []
