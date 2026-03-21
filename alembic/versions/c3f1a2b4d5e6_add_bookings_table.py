"""add_bookings_table

Revision ID: c3f1a2b4d5e6
Revises: e10be14f9da7
Create Date: 2026-03-20 23:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision: str = "c3f1a2b4d5e6"
down_revision: Union[str, None] = "e10be14f9da7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if "bookings" in inspector.get_table_names():
        return
        
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("property_id", sa.Integer(), sa.ForeignKey("properties.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_name",  sa.String(100),  nullable=True),
        sa.Column("customer_email", sa.String(150),  nullable=True),
        sa.Column("customer_phone", sa.String(15),   nullable=True),
        sa.Column("booking_type",
            sa.Enum("pg", "flat", "villa", "plot", "other", name="booking_type_enum"),
            server_default="pg", nullable=False),
        sa.Column("move_in_date", sa.DateTime(), nullable=True),
        sa.Column("notes",        sa.Text(),     nullable=True),
        sa.Column("order_id",   sa.String(100), unique=True, nullable=False),
        sa.Column("payment_id", sa.String(100), nullable=True),
        sa.Column("amount",   sa.DECIMAL(10, 2), nullable=True),
        sa.Column("currency", sa.String(10), server_default="INR", nullable=False),
        sa.Column("payment_status",
            sa.Enum("pending", "paid", "failed", "refunded", name="booking_payment_status_enum"),
            server_default="pending", nullable=False),
        sa.Column("status",
            sa.Enum("pending", "confirmed", "completed", "cancelled", name="booking_status_enum"),
            server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(),
                  onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bookings_order_id",        "bookings", ["order_id"])
    op.create_index("ix_bookings_payment_id",       "bookings", ["payment_id"])
    op.create_index("ix_bookings_property_id",      "bookings", ["property_id"])
    op.create_index("ix_bookings_payment_status",   "bookings", ["payment_status"])
    op.create_index("ix_bookings_status",           "bookings", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    if "bookings" not in inspector.get_table_names():
        return

    op.drop_index("ix_bookings_status",         table_name="bookings")
    op.drop_index("ix_bookings_payment_status", table_name="bookings")
    op.drop_index("ix_bookings_property_id",    table_name="bookings")
    op.drop_index("ix_bookings_payment_id",     table_name="bookings")
    op.drop_index("ix_bookings_order_id",       table_name="bookings")
    op.drop_table("bookings")
    op.execute("DROP TYPE IF EXISTS booking_type_enum")
    op.execute("DROP TYPE IF EXISTS booking_payment_status_enum")
    op.execute("DROP TYPE IF EXISTS booking_status_enum")
