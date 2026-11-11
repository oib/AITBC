"""edge_compute_request_escrow_binding

EDGE-PAY-1 (#1668): ``compute_requests.escrow_id`` records the escrow key
(``job_id``, or legacy ``escrow_id``) whose locked payment authorized the
request, and ``escrow_amount`` keeps the AIT amount the escrow reported at
verification time for settlement/dispute accounting.

``escrow_id`` is unique: one locked escrow authorizes exactly one compute
request. Before this the edge verified ``status == "locked"`` and discarded
the identity, so the same escrow could authorize unlimited submissions and
nothing bound escrow to request.

``init_db``'s ``create_all`` never alters existing columns, so deployments
with a pre-existing edge database need this revision. Fresh databases get
the columns and the unique index from the baseline ``create_all`` (which
runs against current models) — the upgrade detects both and skips, same
pattern as ``8cbdbb088242`` / ``9f2c7a1e4b6d``.

As with ``request_id``, ``CREATE UNIQUE INDEX`` fails loudly if a
pre-constraint database already holds colliding ``escrow_id`` rows — that
collision is the bug being fixed and must be resolved by hand.

Revision ID: c9f2a4b6d8e1
Revises: 9f2c7a1e4b6d
Create Date: 2026-11-11 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "c9f2a4b6d8e1"
down_revision: str | Sequence[str] | None = "9f2c7a1e4b6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_compute_requests_escrow_id"


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table_name: str, column: str) -> bool:
    if context.is_offline_mode():
        return True
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table_name))


def _escrow_index_is_unique(bind: sa.engine.Connection) -> bool:
    """True when the escrow_id index already exists and is unique.

    Offline mode cannot inspect; treat as not-yet-unique so the emitted SQL
    performs the drop+create (idempotent on any database that has the index,
    which every compute_requests table built from current models does).
    """
    if context.is_offline_mode():
        return False
    for idx in sa.inspect(bind).get_indexes("compute_requests"):
        if idx["name"] == _INDEX_NAME:
            return bool(idx.get("unique"))
    return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "compute_requests"):
        return
    if not _column_exists(bind, "compute_requests", "escrow_id"):
        columns = [
            sa.Column("escrow_id", sa.String(), nullable=True),
            sa.Column("escrow_amount", sa.Numeric(20, 8), nullable=True),
        ]
        if bind.dialect.name == "sqlite" and not context.is_offline_mode():
            with op.batch_alter_table("compute_requests", recreate="always") as batch_op:
                for column in columns:
                    batch_op.add_column(column)
        else:
            for column in columns:
                op.add_column("compute_requests", column)
    if _escrow_index_is_unique(bind):
        return
    if not context.is_offline_mode():
        existing = [idx["name"] for idx in sa.inspect(bind).get_indexes("compute_requests")]
        if _INDEX_NAME in existing:
            op.drop_index(_INDEX_NAME, table_name="compute_requests")
    op.create_index(_INDEX_NAME, "compute_requests", ["escrow_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "compute_requests"):
        return
    if _column_exists(bind, "compute_requests", "escrow_id"):
        op.drop_index(_INDEX_NAME, table_name="compute_requests")
        if bind.dialect.name == "sqlite" and not context.is_offline_mode():
            with op.batch_alter_table("compute_requests", recreate="always") as batch_op:
                batch_op.drop_column("escrow_amount")
                batch_op.drop_column("escrow_id")
        else:
            op.drop_column("compute_requests", "escrow_amount")
            op.drop_column("compute_requests", "escrow_id")
