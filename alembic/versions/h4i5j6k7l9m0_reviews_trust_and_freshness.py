"""Reviews trust fields + property freshness timestamps

Revision ID: h4i5j6k7l9m0
Revises: a73d8822d1bc
Create Date: 2026-05-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h4i5j6k7l9m0"
down_revision: Union[str, Sequence[str], None] = "a73d8822d1bc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_names(inspector, table: str) -> set:
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    rcols = _col_names(inspector, "reviews")
    if "status" not in rcols:
        op.add_column(
            "reviews",
            sa.Column("status", sa.String(20), nullable=False, server_default="approved"),
        )
    if "cleanliness_rating" not in rcols:
        op.add_column("reviews", sa.Column("cleanliness_rating", sa.Integer(), nullable=True))
    if "wifi_rating" not in rcols:
        op.add_column("reviews", sa.Column("wifi_rating", sa.Integer(), nullable=True))
    if "food_rating" not in rcols:
        op.add_column("reviews", sa.Column("food_rating", sa.Integer(), nullable=True))
    if "safety_rating" not in rcols:
        op.add_column("reviews", sa.Column("safety_rating", sa.Integer(), nullable=True))
    if "owner_response" not in rcols:
        op.add_column("reviews", sa.Column("owner_response", sa.Text(), nullable=True))
    if "review_images" not in rcols:
        op.add_column("reviews", sa.Column("review_images", sa.JSON(), nullable=True))
    if "verified_stay" not in rcols:
        op.add_column(
            "reviews",
            sa.Column("verified_stay", sa.Boolean(), nullable=False, server_default="0"),
        )
    if "updated_at" not in rcols:
        op.add_column(
            "reviews",
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        )

    pcols = _col_names(inspector, "properties")
    if "last_verified_at" not in pcols:
        op.add_column("properties", sa.Column("last_verified_at", sa.DateTime(), nullable=True))
    if "last_booked_at" not in pcols:
        op.add_column("properties", sa.Column("last_booked_at", sa.DateTime(), nullable=True))
    if "last_review_at" not in pcols:
        op.add_column("properties", sa.Column("last_review_at", sa.DateTime(), nullable=True))

    # Backfill property freshness from existing data
    op.execute(
        """
        UPDATE properties p
        SET last_review_at = (
            SELECT MAX(r.created_at) FROM reviews r
            WHERE r.property_id = p.id
              AND (r.status = 'approved' OR r.status IS NULL)
        )
        WHERE last_review_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE properties
        SET last_verified_at = updated_at
        WHERE last_verified_at IS NULL AND updated_at IS NOT NULL
        """
    )


def downgrade() -> None:
    for col in ("last_review_at", "last_booked_at", "last_verified_at"):
        try:
            op.drop_column("properties", col)
        except Exception:
            pass
    for col in (
        "updated_at",
        "verified_stay",
        "review_images",
        "owner_response",
        "safety_rating",
        "food_rating",
        "wifi_rating",
        "cleanliness_rating",
        "status",
    ):
        try:
            op.drop_column("reviews", col)
        except Exception:
            pass
