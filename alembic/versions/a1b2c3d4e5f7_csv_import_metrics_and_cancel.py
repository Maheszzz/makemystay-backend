"""csv_import metrics columns and cancelled status support

Revision ID: a1b2c3d4e5f7
Revises: 680cea7efa1d
Create Date: 2026-03-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "680cea7efa1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "csv_imports",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "csv_imports",
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("csv_imports", sa.Column("duration_seconds", sa.Float(), nullable=True))
    op.add_column("csv_imports", sa.Column("rows_per_second", sa.Float(), nullable=True))
    op.add_column("csv_imports", sa.Column("failure_rate", sa.Float(), nullable=True))
    op.add_column("csv_imports", sa.Column("success_rate", sa.Float(), nullable=True))
    op.add_column("csv_imports", sa.Column("avg_row_latency_ms", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("csv_imports", "avg_row_latency_ms")
    op.drop_column("csv_imports", "success_rate")
    op.drop_column("csv_imports", "failure_rate")
    op.drop_column("csv_imports", "rows_per_second")
    op.drop_column("csv_imports", "duration_seconds")
    op.drop_column("csv_imports", "processing_completed_at")
    op.drop_column("csv_imports", "processing_started_at")
