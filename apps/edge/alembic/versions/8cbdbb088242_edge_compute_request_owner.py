"""edge_compute_request_owner

EDGE-AUTHZ-BEFORE-COMMISSIONING (#1205): ``compute_requests.owner_id`` records
the JWT ``sub`` of the submitter so serve list/read/cancel can be scoped to the
owner (admin bypass, matching the #1188 ownership model).

Nullable with no backfill: rows predating the column keep ``NULL`` and are
admin-only until claimed — the correct fail-closed default, and the compute
tier has no live deployment to migrate anyway.

``init_db``'s ``create_all`` never alters existing columns, so deployments with
a pre-existing edge database need this revision. Fresh databases get the column
from the baseline ``create_all`` (which runs against current models), hence the
existence guard — same pattern as ``e1c47b09f2a6``.

Revision ID: 8cbdbb088242
Revises: e1c47b09f2a6
Create Date: 2026-11-06 00:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "8cbdbb088242"
down_revision: str | Sequence[str] | None = "e1c47b09f2a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table_name: str, column: str) -> bool:
    if context.is_offline_mode():
        return True
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "compute_requests") or _column_exists(bind, "compute_requests", "owner_id"):
        return
    if bind.dialect.name == "sqlite" and not context.is_offline_mode():
        with op.batch_alter_table("compute_requests", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("owner_id", sa.String(), nullable=True))
    else:
        op.add_column("compute_requests", sa.Column("owner_id", sa.String(), nullable=True))
    op.create_index("ix_compute_requests_owner_id", "compute_requests", ["owner_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "compute_requests") or not _column_exists(bind, "compute_requests", "owner_id"):
        return
    op.drop_index("ix_compute_requests_owner_id", table_name="compute_requests")
    if bind.dialect.name == "sqlite" and not context.is_offline_mode():
        with op.batch_alter_table("compute_requests", recreate="always") as batch_op:
            batch_op.drop_column("owner_id")
    else:
        op.drop_column("compute_requests", "owner_id")
