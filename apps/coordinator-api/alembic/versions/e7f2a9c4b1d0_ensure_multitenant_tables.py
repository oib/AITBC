"""ensure multitenant tables exist on historical upgrades

Revision ID: e7f2a9c4b1d0
Revises: f53990f9d6cc
Create Date: 2026-09-08 16:40:00.000000+00:00

The eight tenant_* tables (tenants, tenant_users, tenant_quotas,
usage_records, invoices, tenant_api_keys, tenant_audit_logs, tenant_metrics)
are only ever created by ``001_initial_migration``'s ``create_all``, which
runs solely on fresh databases. A database whose history predates the
multitenant feature can ``alembic upgrade head`` and still lack all eight —
proven on the 2026-08-09 coordinator.db backup (stamped 236edfbd9728). This
migration creates them with ``checkfirst`` so both paths converge.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f2a9c4b1d0"
down_revision: str | Sequence[str] | None = "f53990f9d6cc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_TABLES = {
    "tenants",
    "tenant_users",
    "tenant_quotas",
    "usage_records",
    "invoices",
    "tenant_api_keys",
    "tenant_audit_logs",
    "tenant_metrics",
}


def _tenant_tables_sorted():
    import coordinator_api.models.multitenant  # noqa: F401
    from sqlmodel import SQLModel

    # sorted_tables is FK-dependency ordered; keep only the tenant set.
    return [t for t in SQLModel.metadata.sorted_tables if t.name in _TENANT_TABLES]


def upgrade() -> None:
    bind = op.get_bind()
    for table in _tenant_tables_sorted():
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(_tenant_tables_sorted()):
        table.drop(bind, checkfirst=True)
