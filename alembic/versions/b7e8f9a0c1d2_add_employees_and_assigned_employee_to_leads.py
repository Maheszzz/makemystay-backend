"""add employees table and leads.assigned_employee_id

Revision ID: b7e8f9a0c1d2
Revises: cd61ded70119
Create Date: 2026-03-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e8f9a0c1d2"
down_revision: Union[str, Sequence[str], None] = "cd61ded70119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("employee_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("role", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_employees_user_id_users")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", name=op.f("uq_employees_employee_id")),
    )
    op.create_index(op.f("ix_employees_employee_id"), "employees", ["employee_id"], unique=False)
    op.create_index(op.f("ix_employees_id"), "employees", ["id"], unique=False)
    op.create_index(op.f("ix_employees_status"), "employees", ["status"], unique=False)
    op.create_index(op.f("ix_employees_user_id"), "employees", ["user_id"], unique=False)

    op.add_column("leads", sa.Column("assigned_employee_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_leads_assigned_employee_id_employees"),
        "leads",
        "employees",
        ["assigned_employee_id"],
        ["id"],
    )
    op.create_index(op.f("ix_leads_assigned_employee_id"), "leads", ["assigned_employee_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_leads_assigned_employee_id"), table_name="leads")
    op.drop_constraint(op.f("fk_leads_assigned_employee_id_employees"), "leads", type_="foreignkey")
    op.drop_column("leads", "assigned_employee_id")

    op.drop_index(op.f("ix_employees_user_id"), table_name="employees")
    op.drop_index(op.f("ix_employees_status"), table_name="employees")
    op.drop_index(op.f("ix_employees_id"), table_name="employees")
    op.drop_index(op.f("ix_employees_employee_id"), table_name="employees")
    op.drop_table("employees")
