"""Migrate UsageRecord, TenantQuota, and Invoice monetary columns from Float to Numeric

Changes Float columns to Numeric(18, 8) for precise decimal arithmetic,
preventing accounting drift in billing and quota tracking.

Affected tables (in the ``aitbc`` schema):
- ``usage_records``: quantity, unit_price, total_cost
- ``tenant_quotas``: limit_value, used_value
- ``invoices``: subtotal, tax_amount, total_amount

Revision ID: migrate_usage_records_to_numeric
Revises: add_query_performance_indexes
Create Date: 2026-07-05 00:00:00.000000

"""

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "migrate_usage_records_to_numeric"
down_revision = "migrate_marketplace_to_numeric"
branch_labels = None
depends_on = None


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name.split(".")[-1] in sa.inspect(bind).get_table_names()


# (table, column, old_type, new_type) for each migration.
# Using if_not_exists=True via batch_alter_table for SQLite compatibility.
_COLUMNS: list[tuple[str, str, str, str]] = [
    # usage_records
    ("aitbc.usage_records", "quantity", "FLOAT", "NUMERIC(18, 8)"),
    ("aitbc.usage_records", "unit_price", "FLOAT", "NUMERIC(18, 8)"),
    ("aitbc.usage_records", "total_cost", "FLOAT", "NUMERIC(18, 8)"),
    # tenant_quotas
    ("aitbc.tenant_quotas", "limit_value", "FLOAT", "NUMERIC(18, 8)"),
    ("aitbc.tenant_quotas", "used_value", "FLOAT", "NUMERIC(18, 8)"),
    # invoices
    ("aitbc.invoices", "subtotal", "FLOAT", "NUMERIC(18, 8)"),
    ("aitbc.invoices", "tax_amount", "FLOAT", "NUMERIC(18, 8)"),
    ("aitbc.invoices", "total_amount", "FLOAT", "NUMERIC(18, 8)"),
]


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, _old_type, _new_type in _COLUMNS:
        if not _table_exists(bind, table):
            continue
        if bind.dialect.name == "sqlite" and not context.is_offline_mode():
            with op.batch_alter_table(table.split(".")[-1], recreate="always") as batch_op:
                batch_op.alter_column(
                    column_name=column,
                    type_=sa.Numeric(18, 8),
                    existing_type=sa.Float(),
                    nullable=False,
                )
        else:
            op.alter_column(
                table_name=table,
                column_name=column,
                type_=sa.Numeric(18, 8),
                existing_type=sa.Float(),
                nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    for table, column, _old_type, _new_type in _COLUMNS:
        if not _table_exists(bind, table):
            continue
        if bind.dialect.name == "sqlite" and not context.is_offline_mode():
            with op.batch_alter_table(table.split(".")[-1], recreate="always") as batch_op:
                batch_op.alter_column(
                    column_name=column,
                    type_=sa.Float(),
                    existing_type=sa.Numeric(18, 8),
                    nullable=False,
                )
        else:
            op.alter_column(
                table_name=table,
                column_name=column,
                type_=sa.Float(),
                existing_type=sa.Numeric(18, 8),
                nullable=False,
            )
