"""edge_compute_requests_request_id_unique

EDGE-RESULT-1 (#1685): ``compute_requests.request_id`` is the public lookup
key behind ``scalar_one_or_none`` reads in get/cancel/result paths. It was
minted as ``req_<8 hex>`` (~4G space) behind a plain index, so a
birthday-bound collision made every read for the id raise
``MultipleResultsFound`` -> HTTP 500 for both victims. The schema now mints
full-uuid4 ids and declares the column unique; this revision converges
databases created before the constraint existed.

``init_db``'s ``create_all`` never alters existing indexes, so deployments
with a pre-existing edge database need this revision. Fresh databases get
the unique index from the baseline ``create_all`` (which runs against
current models) — the upgrade detects it and skips, same pattern as
``8cbdbb088242``.

The unique index is created only after checking for existing duplicates is
the caller's problem: if a pre-constraint database already holds colliding
``request_id`` rows, ``CREATE UNIQUE INDEX`` fails loudly rather than
silently picking a winner — the collision is the bug being fixed, so it
must be resolved by hand, not migrated around.

Revision ID: 9f2c7a1e4b6d
Revises: 8cbdbb088242
Create Date: 2026-11-11 00:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "9f2c7a1e4b6d"
down_revision: str | Sequence[str] | None = "8cbdbb088242"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_compute_requests_request_id"


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


def _request_id_index_is_unique(bind: sa.engine.Connection) -> bool:
    """True when the request_id index already exists and is unique.

    Offline mode cannot inspect; treat as not-yet-unique so the emitted SQL
    performs the drop+create (idempotent on any database that has the index,
    which every compute_requests table does — the column has been indexed
    since the baseline).
    """
    if context.is_offline_mode():
        return False
    for idx in sa.inspect(bind).get_indexes("compute_requests"):
        if idx["name"] == _INDEX_NAME:
            return bool(idx.get("unique"))
    return False


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "compute_requests") or _request_id_index_is_unique(bind):
        return
    op.drop_index(_INDEX_NAME, table_name="compute_requests")
    op.create_index(_INDEX_NAME, "compute_requests", ["request_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "compute_requests"):
        return
    op.drop_index(_INDEX_NAME, table_name="compute_requests")
    op.create_index(_INDEX_NAME, "compute_requests", ["request_id"])
