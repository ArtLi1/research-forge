import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CandidateScheme(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidate_schemes"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(32), default="candidate", index=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    langgraph_thread_id: Mapped[str] = mapped_column(String(255), index=True)
    abandoned_reason: Mapped[str | None] = mapped_column(Text)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CandidateVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "candidate_versions"
    __table_args__ = (UniqueConstraint("candidate_id", "version_number"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_schemes.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_versions.id", ondelete="SET NULL")
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    user_instruction: Mapped[str | None] = mapped_column(Text)
    risk_assessment: Mapped[dict[str, Any]] = mapped_column(JSON)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgentRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "agent_runs"
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("background_tasks.id", ondelete="SET NULL"), unique=True
    )
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_schemes.id", ondelete="SET NULL"), index=True
    )
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    run_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSON)
    output: Mapped[dict[str, Any]] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(255))
    prompt_version: Mapped[str] = mapped_column(String(64))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
