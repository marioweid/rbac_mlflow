"""Move datasets from team-scoped to experiment-scoped; add digest to dataset_versions

Revision ID: 003
Revises: 002
Create Date: 2026-03-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── datasets table ────────────────────────────────────────────────────────

    # Add new column (nullable first for data migration)
    op.add_column("datasets", sa.Column("mlflow_experiment_id", sa.Text(), nullable=True))

    # Data migration: map each dataset's team_id to the first matching
    # mlflow_experiment_id via team_experiments. DISTINCT ON is PostgreSQL syntax.
    op.execute("""
        UPDATE datasets d
        SET mlflow_experiment_id = te.mlflow_experiment_id
        FROM (
            SELECT DISTINCT ON (team_id) team_id, mlflow_experiment_id
            FROM team_experiments
            ORDER BY team_id
        ) te
        WHERE d.team_id = te.team_id
    """)

    # Any datasets with no matching team_experiment get a sentinel value
    op.execute("""
        UPDATE datasets
        SET mlflow_experiment_id = 'UNLINKED'
        WHERE mlflow_experiment_id IS NULL
    """)

    # Make it NOT NULL now that all rows have a value
    op.alter_column("datasets", "mlflow_experiment_id", nullable=False)

    # Drop old constraints / columns
    op.drop_constraint("uq_dataset_name_team", "datasets", type_="unique")
    op.drop_index("ix_datasets_team_id", "datasets")
    op.drop_column("datasets", "team_id")

    # Add new constraint and index
    op.create_unique_constraint(
        "uq_dataset_name_experiment", "datasets", ["name", "mlflow_experiment_id"]
    )
    op.create_index("ix_datasets_experiment_id", "datasets", ["mlflow_experiment_id"])

    # ── dataset_versions table ────────────────────────────────────────────────

    op.add_column(
        "dataset_versions",
        sa.Column("digest", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    # Re-add team_id (data will be lost; suitable for dev environments)
    op.add_column(
        "datasets",
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.drop_constraint("uq_dataset_name_experiment", "datasets", type_="unique")
    op.drop_index("ix_datasets_experiment_id", "datasets")
    op.drop_column("datasets", "mlflow_experiment_id")
    op.create_unique_constraint("uq_dataset_name_team", "datasets", ["name", "team_id"])
    op.create_index("ix_datasets_team_id", "datasets", ["team_id"])

    op.drop_column("dataset_versions", "digest")
