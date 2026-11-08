"""gpu_bookings.payment_id — per-booking payment binding (#1231)

Revision ID: g1b2c3d4e5f6
Revises: f5a6b7c8d9e0
Create Date: 2026-11-08 00:00:00.000000+00:00

R14-07-F1: purchase-path GPU bookings share job_id across siblings on one
prepared job, so the paid-hold expiry check could not tell which booking a
paid JobPayment belonged to. Persist the booking's own payment id; NULL
for book_gpu holds, which keep the legacy job-linkage check.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "g1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if context.is_offline_mode():
        # No database to inspect: emit the DDL unconditionally.
        existing: set[str] = set()
        indexes: set[str] = set()
    else:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        if "gpu_bookings" not in inspector.get_table_names():
            return
        existing = {c["name"] for c in inspector.get_columns("gpu_bookings")}
        indexes = {idx["name"] for idx in inspector.get_indexes("gpu_bookings")}
    if "payment_id" not in existing:
        op.add_column("gpu_bookings", sa.Column("payment_id", sa.String(length=64), nullable=True))
    if "ix_gpu_bookings_payment_id" not in indexes:
        op.create_index("ix_gpu_bookings_payment_id", "gpu_bookings", ["payment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_gpu_bookings_payment_id", table_name="gpu_bookings", if_exists=True)
    op.drop_column("gpu_bookings", "payment_id")
