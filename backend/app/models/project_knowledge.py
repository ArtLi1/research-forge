import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ProjectKnowledge(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "project_knowledge"
    __table_args__ = (UniqueConstraint("project_id", "category"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(64))
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProjectKnowledgeVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "project_knowledge_versions"
    __table_args__ = (UniqueConstraint("project_knowledge_id", "version_number"),)

    project_knowledge_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_knowledge.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    change_summary: Mapped[str] = mapped_column(Text)
    source_paper_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_idea_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserIdea(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_ideas"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    idea_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    linked_paper_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    linked_evidence_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    agent_evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSON)
