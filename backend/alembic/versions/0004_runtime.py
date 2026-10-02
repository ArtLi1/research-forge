"""Durable task leases and research checkpoints.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("attempts", "dispatch_count"):
        op.add_column(
            "background_tasks", sa.Column(name, sa.Integer(), nullable=False, server_default="0")
        )
    op.add_column("background_tasks", sa.Column("dispatched_at", sa.DateTime(timezone=True)))
    op.add_column("background_tasks", sa.Column("lease_token", sa.Uuid()))
    op.add_column("background_tasks", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column("background_tasks", sa.Column("active_key", sa.String(100)))
    op.create_unique_constraint(
        "uq_background_tasks_active_key", "background_tasks", ["active_key"]
    )
    op.create_index(
        "ix_background_tasks_lease_expires_at", "background_tasks", ["lease_expires_at"]
    )
    op.add_column("agent_runs", sa.Column("task_id", sa.Uuid()))
    op.add_column(
        "agent_runs",
        sa.Column("checkpoint", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.create_foreign_key(
        "fk_agent_runs_task_id",
        "agent_runs",
        "background_tasks",
        ["task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_agent_runs_task_id", "agent_runs", ["task_id"])
    # Old workers must be stopped before upgrade: they do not understand lease fences.
    op.execute("""
        UPDATE background_tasks SET status = 'queued', stage = 'queued', rq_job_id = NULL,
            message = '工作流升级，等待重新派发', finished_at = NULL
        WHERE status IN ('queued', 'running')
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY resource_id ORDER BY created_at DESC, id DESC
            ) AS ordinal FROM background_tasks
            WHERE status = 'queued' AND resource_type = 'paper' AND resource_id IS NOT NULL
        ) UPDATE background_tasks SET status = 'failed', stage = 'failed',
            message = '已有较新的论文处理任务', finished_at = CURRENT_TIMESTAMP
        WHERE id IN (SELECT id FROM ranked WHERE ordinal > 1)
    """)
    op.execute("""
        UPDATE background_tasks SET active_key = 'paper:' || resource_id::text
        WHERE status = 'queued' AND resource_type = 'paper' AND resource_id IS NOT NULL
    """)
    op.execute("""
        UPDATE agent_runs SET status = 'failed', error = '工作流升级，旧执行已中断',
            finished_at = CURRENT_TIMESTAMP WHERE status = 'running'
    """)


def downgrade() -> None:
    op.drop_constraint("uq_agent_runs_task_id", "agent_runs", type_="unique")
    op.drop_constraint("fk_agent_runs_task_id", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "checkpoint")
    op.drop_column("agent_runs", "task_id")
    op.drop_index("ix_background_tasks_lease_expires_at", "background_tasks")
    op.drop_constraint("uq_background_tasks_active_key", "background_tasks", type_="unique")
    for name in (
        "active_key",
        "lease_expires_at",
        "lease_token",
        "dispatched_at",
        "dispatch_count",
        "attempts",
    ):
        op.drop_column("background_tasks", name)
