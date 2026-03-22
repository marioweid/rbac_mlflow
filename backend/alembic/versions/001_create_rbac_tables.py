"""Create RBAC tables: teams, group_role_mappings, team_experiments, audit_events

Revision ID: 001
Revises:
Create Date: 2026-03-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "group_role_mappings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("group_name", sa.String(255), nullable=False),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(50), nullable=False),
        sa.UniqueConstraint("group_name", "team_id", name="uq_group_team"),
    )

    op.create_table(
        "team_experiments",
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("mlflow_experiment_id", sa.Text(), primary_key=True),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_sub", sa.Text(), nullable=False),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_audit_events_user_sub", "audit_events", ["user_sub"])
    op.create_index("ix_audit_events_team_id", "audit_events", ["team_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("team_experiments")
    op.drop_table("group_role_mappings")
    op.drop_table("teams")
