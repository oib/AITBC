"""Drop unused pricing tables

Removes three pricing tables that were never wired into any service and had no
read/write callers (confirmed during v0.5.19 tech-debt cleanup):

- ``pricing_optimizations`` (PricingOptimization) — no experiment/A-B-test use case
- ``pricing_alerts``         (PricingAlert)         — no alerting use case
- ``pricing_rules``          (PricingRule)          — no rule-based pricing use case

Also drops the leftover ``price_forecast`` (singular) table that was a dead
duplicate of the trading context's ``price_forecasts`` (plural) table, defined
in the marketplace context's ``gpu_marketplace.py`` but never imported or used.

The corresponding SQLModel classes were removed from
``pricing_models.py`` / ``gpu_marketplace.py``. ``pricing_audit_log`` is
retained — it is wired into ``dynamic_pricing.py`` as the audit trail for
automated price changes and strategy updates.

The drops are guarded by an existence check so the migration is safe to run on
databases that never created the tables (e.g. fresh DBs created after the model
removal, or DBs that only ran a subset of migrations).

Revision ID: drop_unused_pricing_tables
Revises: add_query_performance_indexes
Create Date: 2026-06-29 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "drop_unused_pricing_tables"
down_revision = "add_query_performance_indexes"
branch_labels = None
depends_on = None


# Tables to drop, in dependency-safe order. The marketplace leftover
# ``price_forecast`` (singular) is included alongside the three trading tables.
_TABLES_TO_DROP: list[str] = [
    "pricing_optimizations",
    "pricing_alerts",
    "pricing_rules",
    "price_forecast",  # singular — marketplace leftover (NOT trading's price_forecasts)
]


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    """Drop the unused pricing tables (idempotent)."""
    bind = op.get_bind()
    for table_name in _TABLES_TO_DROP:
        if _table_exists(bind, table_name):
            op.drop_table(table_name)


def downgrade() -> None:
    """Recreate the dropped tables.

    The tables are recreated as bare schemas (no indexes) because the original
    SQLModel classes have been removed. This is a best-effort downgrade to
    preserve migration reversibility; the data is not recoverable.
    """
    bind = op.get_bind()

    if not _table_exists(bind, "price_forecast"):
        op.create_table(
            "price_forecast",
            sa.Column("id", sa.String(), nullable=False, primary_key=True),
            sa.Column("resource_id", sa.String(), nullable=True),
            sa.Column("forecast_timestamp", sa.DateTime(), nullable=True),
            sa.Column("predicted_price", sa.Float(), nullable=True),
            sa.Column("confidence_lower", sa.Float(), nullable=True),
            sa.Column("confidence_upper", sa.Float(), nullable=True),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column("model_version", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )

    if not _table_exists(bind, "pricing_optimizations"):
        op.create_table(
            "pricing_optimizations",
            sa.Column("id", sa.String(), nullable=False, primary_key=True),
            sa.Column("experiment_id", sa.String(), nullable=True),
            sa.Column("provider_id", sa.String(), nullable=True),
            sa.Column("resource_type", sa.String(), nullable=True),
            sa.Column("experiment_name", sa.String(), nullable=False),
            sa.Column("experiment_type", sa.String(), nullable=False),
            sa.Column("hypothesis", sa.String(), nullable=False),
            sa.Column("control_strategy", sa.String(), nullable=False),
            sa.Column("test_strategy", sa.String(), nullable=False),
            sa.Column("sample_size", sa.Integer(), nullable=False),
            sa.Column("confidence_level", sa.Float(), nullable=True),
            sa.Column("statistical_power", sa.Float(), nullable=True),
            sa.Column("minimum_detectable_effect", sa.Float(), nullable=False),
            sa.Column("regions", sa.JSON(), nullable=True),
            sa.Column("duration_days", sa.Integer(), nullable=False),
            sa.Column("start_date", sa.DateTime(), nullable=False),
            sa.Column("end_date", sa.DateTime(), nullable=True),
            sa.Column("control_performance", sa.JSON(), nullable=True),
            sa.Column("test_performance", sa.JSON(), nullable=True),
            sa.Column("statistical_significance", sa.Float(), nullable=True),
            sa.Column("effect_size", sa.Float(), nullable=True),
            sa.Column("revenue_impact", sa.Float(), nullable=True),
            sa.Column("profit_impact", sa.Float(), nullable=True),
            sa.Column("market_share_impact", sa.Float(), nullable=True),
            sa.Column("customer_satisfaction_impact", sa.Float(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("conclusion", sa.String(), nullable=True),
            sa.Column("recommendations", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("reviewed_by", sa.String(), nullable=True),
            sa.Column("approved_by", sa.String(), nullable=True),
        )

    if not _table_exists(bind, "pricing_alerts"):
        op.create_table(
            "pricing_alerts",
            sa.Column("id", sa.String(), nullable=False, primary_key=True),
            sa.Column("provider_id", sa.String(), nullable=True),
            sa.Column("resource_id", sa.String(), nullable=True),
            sa.Column("resource_type", sa.String(), nullable=True),
            sa.Column("alert_type", sa.String(), nullable=True),
            sa.Column("severity", sa.String(), nullable=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("trigger_conditions", sa.JSON(), nullable=True),
            sa.Column("threshold_values", sa.JSON(), nullable=True),
            sa.Column("actual_values", sa.JSON(), nullable=True),
            sa.Column("market_conditions", sa.JSON(), nullable=True),
            sa.Column("strategy_context", sa.JSON(), nullable=True),
            sa.Column("historical_context", sa.JSON(), nullable=True),
            sa.Column("recommendations", sa.JSON(), nullable=True),
            sa.Column("automated_actions_taken", sa.JSON(), nullable=True),
            sa.Column("manual_actions_required", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("resolution", sa.String(), nullable=True),
            sa.Column("resolution_notes", sa.Text(), nullable=True),
            sa.Column("business_impact", sa.String(), nullable=True),
            sa.Column("revenue_impact_estimate", sa.Float(), nullable=True),
            sa.Column("customer_impact_estimate", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("first_seen", sa.DateTime(), nullable=True),
            sa.Column("last_seen", sa.DateTime(), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.Column("notification_sent", sa.Boolean(), nullable=True),
            sa.Column("notification_channels", sa.JSON(), nullable=True),
            sa.Column("escalation_level", sa.Integer(), nullable=True),
        )

    if not _table_exists(bind, "pricing_rules"):
        op.create_table(
            "pricing_rules",
            sa.Column("id", sa.String(), nullable=False, primary_key=True),
            sa.Column("provider_id", sa.String(), nullable=True),
            sa.Column("strategy_id", sa.String(), nullable=True),
            sa.Column("rule_name", sa.String(), nullable=False),
            sa.Column("rule_description", sa.String(), nullable=True),
            sa.Column("rule_type", sa.String(), nullable=False),
            sa.Column("condition_expression", sa.String(), nullable=False),
            sa.Column("action_expression", sa.String(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=True),
            sa.Column("resource_types", sa.JSON(), nullable=True),
            sa.Column("regions", sa.JSON(), nullable=True),
            sa.Column("time_conditions", sa.JSON(), nullable=True),
            sa.Column("parameters", sa.JSON(), nullable=True),
            sa.Column("thresholds", sa.JSON(), nullable=True),
            sa.Column("multipliers", sa.JSON(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=True),
            sa.Column("execution_count", sa.Integer(), nullable=True),
            sa.Column("success_count", sa.Integer(), nullable=True),
            sa.Column("failure_count", sa.Integer(), nullable=True),
            sa.Column("last_executed", sa.DateTime(), nullable=True),
            sa.Column("last_success", sa.DateTime(), nullable=True),
            sa.Column("average_execution_time", sa.Float(), nullable=True),
            sa.Column("success_rate", sa.Float(), nullable=True),
            sa.Column("business_impact", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("updated_by", sa.String(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=True),
            sa.Column("change_log", sa.JSON(), nullable=True),
        )
