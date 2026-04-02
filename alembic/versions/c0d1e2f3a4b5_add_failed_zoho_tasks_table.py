"""add failed_zoho_tasks dlq table

Revision ID: c0d1e2f3a4b5
Revises: a8b9c0d1e2f3
Create Date: 2026-04-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "failed_zoho_tasks" in inspector.get_table_names():
        return
    op.create_table(
        "failed_zoho_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_failed_zoho_tasks_lead_id"), "failed_zoho_tasks", ["lead_id"], unique=False)
    op.create_index(op.f("ix_failed_zoho_tasks_created_at"), "failed_zoho_tasks", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_failed_zoho_tasks_created_at"), table_name="failed_zoho_tasks")
    op.drop_index(op.f("ix_failed_zoho_tasks_lead_id"), table_name="failed_zoho_tasks")
    op.drop_table("failed_zoho_tasks")
