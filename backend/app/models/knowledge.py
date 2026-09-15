import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PaperKnowledgeCard(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "paper_knowledge_cards"

    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), unique=True, index=True
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(32), default="generated")


class PaperKnowledgeVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "paper_knowledge_versions"
    __table_args__ = (UniqueConstraint("card_id", "version_number"),)

    card_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_knowledge_cards.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    extraction_model: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(64))
    validation_status: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Evidence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "evidence"

    paper_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("papers.id", ondelete="CASCADE"), index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("paper_chunks.id", ondelete="CASCADE"), index=True
    )
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(index=True)
    field_path: Mapped[str] = mapped_column(String(500))
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(1000))
    quote: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MetadataDefinition(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "metadata_definitions"

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(String(32), index=True)
    value_type: Mapped[str] = mapped_column(String(32))
    options: Mapped[list[Any] | None] = mapped_column(JSON)
    auto_extract: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
