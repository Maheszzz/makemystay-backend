"""add file_size to property_images

Revision ID: f8a9b0c1d2e3
Revises: e5f6a7b8c9d0
Create Date: 2026-04-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("property_images"):
        return
    cols = {c["name"] for c in inspector.get_columns("property_images")}
    if "file_size" not in cols:
        op.add_column(
            "property_images",
            sa.Column("file_size", sa.BigInteger(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("property_images"):
        return
    cols = {c["name"] for c in inspector.get_columns("property_images")}
    if "file_size" in cols:
        op.drop_column("property_images", "file_size")
