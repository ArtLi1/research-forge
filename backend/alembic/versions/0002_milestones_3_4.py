"""Milestones 3-4 schema.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metadata_definitions",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("auto_extract", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_metadata_definitions_scope", "metadata_definitions", ["scope"])
    op.create_table(
        "paper_knowledge_cards",
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id"),
    )
    op.create_index(
        "ix_paper_knowledge_cards_current_version_id",
        "paper_knowledge_cards",
        ["current_version_id"],
    )
    op.create_index(
        "ix_paper_knowledge_cards_paper_id",
        "paper_knowledge_cards",
        ["paper_id"],
        unique=True,
    )
    op.create_table(
        "paper_knowledge_versions",
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("extraction_model", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["paper_knowledge_cards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("card_id", "version_number"),
    )
    op.create_index(
        "ix_paper_knowledge_versions_card_id",
        "paper_knowledge_versions",
        ["card_id"],
    )
    op.create_table(
        "evidence",
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("field_path", sa.String(length=500), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("section", sa.String(length=1000), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["paper_chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in ("paper_id", "chunk_id", "target_type", "target_id"):
        op.create_index(f"ix_evidence_{name}", "evidence", [name])
    op.create_table(
        "project_knowledge",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "category"),
    )
    op.create_index("ix_project_knowledge_project_id", "project_knowledge", ["project_id"])
    op.create_table(
        "project_knowledge_versions",
        sa.Column("project_knowledge_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=False),
        sa.Column("source_paper_ids", sa.JSON(), nullable=False),
        sa.Column("source_idea_ids", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_knowledge_id"],
            ["project_knowledge.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_knowledge_id", "version_number"),
    )
    op.create_index(
        "ix_project_knowledge_versions_project_knowledge_id",
        "project_knowledge_versions",
        ["project_knowledge_id"],
    )
    op.create_table(
        "user_ideas",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("idea_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("linked_paper_ids", sa.JSON(), nullable=False),
        sa.Column("linked_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("agent_evaluation", sa.JSON(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_ideas_project_id", "user_ideas", ["project_id"])
    op.create_index("ix_user_ideas_status", "user_ideas", ["status"])


def downgrade() -> None:
    op.drop_table("user_ideas")
    op.drop_table("project_knowledge_versions")
    op.drop_table("project_knowledge")
    op.drop_table("evidence")
    op.drop_table("paper_knowledge_versions")
    op.drop_table("paper_knowledge_cards")
    op.drop_table("metadata_definitions")
