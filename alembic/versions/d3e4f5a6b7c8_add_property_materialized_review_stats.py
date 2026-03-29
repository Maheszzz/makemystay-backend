"""Materialize avg_rating and review_count on properties

Revision ID: d3e4f5a6b7c8
Revises: b1c2d3e4f5a6
Create Date: 2026-03-29 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("properties")}

    if "avg_rating" not in cols:
        op.add_column(
            "properties",
            sa.Column("avg_rating", sa.Numeric(4, 2), nullable=True),
        )
    if "review_count" not in cols:
        op.add_column(
            "properties",
            sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
        )

    # Backfill from reviews (idempotent)
    op.execute(
        """
        UPDATE properties p
        LEFT JOIN (
            SELECT property_id, AVG(rating) AS ar, COUNT(*) AS cnt
            FROM reviews
            GROUP BY property_id
        ) r ON p.id = r.property_id
        SET p.avg_rating = r.ar, p.review_count = COALESCE(r.cnt, 0)
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("properties")}
    if "review_count" in cols:
        op.drop_column("properties", "review_count")
    if "avg_rating" in cols:
        op.drop_column("properties", "avg_rating")
