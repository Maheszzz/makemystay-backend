"""employees: phone and role NOT NULL (production-safe defaults)

Revision ID: e4f5a6b7c8d9
Revises: b7e8f9a0c1d2
Create Date: 2026-03-25

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "b7e8f9a0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE employees SET phone = '' WHERE phone IS NULL"))
    op.execute(sa.text("UPDATE employees SET role = 'RM' WHERE role IS NULL OR role = ''"))

    op.alter_column(
        "employees",
        "phone",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default="",
    )
    op.alter_column(
        "employees",
        "role",
        existing_type=sa.String(length=80),
        nullable=False,
        server_default="RM",
    )
    op.create_index(op.f("ix_employees_role"), "employees", ["role"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_employees_role"), table_name="employees")
    op.alter_column(
        "employees",
        "role",
        existing_type=sa.String(length=80),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "employees",
        "phone",
        existing_type=sa.String(length=32),
        nullable=True,
        server_default=None,
    )
