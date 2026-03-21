"""Add sync_jobs table for celery

Revision ID: 2e8161703e76
Revises: 6a12dabf28e9
Create Date: 2026-03-21 13:06:13.997964

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '2e8161703e76'
down_revision: Union[str, Sequence[str], None] = '6a12dabf28e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table("sync_jobs"):
        op.create_table(
            "sync_jobs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("task_id", sa.String(length=255), nullable=False),
            sa.Column("task_name", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=True),
            sa.Column("result", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_sync_job_indexes = {idx["name"] for idx in inspector.get_indexes("sync_jobs")}
    if op.f("ix_sync_jobs_id") not in existing_sync_job_indexes:
        op.create_index(op.f("ix_sync_jobs_id"), "sync_jobs", ["id"], unique=False)
    if op.f("ix_sync_jobs_status") not in existing_sync_job_indexes:
        op.create_index(op.f("ix_sync_jobs_status"), "sync_jobs", ["status"], unique=False)
    if op.f("ix_sync_jobs_task_id") not in existing_sync_job_indexes:
        op.create_index(op.f("ix_sync_jobs_task_id"), "sync_jobs", ["task_id"], unique=True)

    # NOTE:
    # This migration is for sync_jobs only. Do not mutate property_images indexes
    # here; that causes production failures where idx_property participates in FK plans.


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)

    # Keep property_images indexes untouched in this migration.

    if inspector.has_table("sync_jobs"):
        existing_sync_job_indexes = {idx["name"] for idx in inspector.get_indexes("sync_jobs")}
        if op.f("ix_sync_jobs_task_id") in existing_sync_job_indexes:
            op.drop_index(op.f("ix_sync_jobs_task_id"), table_name="sync_jobs")
        if op.f("ix_sync_jobs_status") in existing_sync_job_indexes:
            op.drop_index(op.f("ix_sync_jobs_status"), table_name="sync_jobs")
        if op.f("ix_sync_jobs_id") in existing_sync_job_indexes:
            op.drop_index(op.f("ix_sync_jobs_id"), table_name="sync_jobs")
        op.drop_table("sync_jobs")
