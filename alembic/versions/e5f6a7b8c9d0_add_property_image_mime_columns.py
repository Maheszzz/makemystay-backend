"""add content_type and mime_validated to property_images

Revision ID: e5f6a7b8c9d0
Revises: c0d1e2f3a4b5
Create Date: 2026-04-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("property_images"):
        return
    cols = {c["name"] for c in inspector.get_columns("property_images")}
    if "content_type" not in cols:
        op.add_column(
            "property_images",
            sa.Column(
                "content_type",
                sa.String(length=80),
                nullable=False,
                server_default="image/jpeg",
            ),
        )
    if "mime_validated" not in cols:
        op.add_column(
            "property_images",
            sa.Column(
                "mime_validated",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("property_images"):
        return
    cols = {c["name"] for c in inspector.get_columns("property_images")}
    if "mime_validated" in cols:
        op.drop_column("property_images", "mime_validated")
    if "content_type" in cols:
        op.drop_column("property_images", "content_type")
