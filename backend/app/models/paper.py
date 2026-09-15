import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Paper(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "papers"

    title: Mapped[str] = mapped_column(String(1000))
    normalized_title: Mapped[str] = mapped_column(String(1000), index=True)
    authors: Mapped[list[str]] = mapped_column(JSON, default=list)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    venue: Mapped[str | None] = mapped_column(String(500))
    doi: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    arxiv_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    abstract: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    file_path: Mapped[str] = mapped_column(String(2000))
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="upload")
    source_url: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    parse_error: Mapped[str | None] = mapped_column(Text)
    global_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PaperSection(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "paper_sections"
    __table_args__ = (UniqueConstraint("paper_id", "order_index"),)

    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(1000))
    level: Mapped[int] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("paper_sections.id", ondelete="SET NULL")
    )


class PaperChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "paper_chunks"
    __table_args__ = (UniqueConstraint("paper_id", "order_index"),)

    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("paper_sections.id", ondelete="SET NULL"), index=True
    )
    chunk_type: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int] = mapped_column(Integer)
    page_end: Mapped[int] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    chroma_id: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
