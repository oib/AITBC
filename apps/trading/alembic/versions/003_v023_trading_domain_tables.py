"""v0.23 the rest of the trading schema: seven tables, five columns, 27 indexes

Revision ID: 003
Revises: 002
Create Date: 2026-08-16 09:28:55

`alembic upgrade head` did not build this service's schema. It built two tables of nine.

The seven in ``domain/trading.py`` -- trade_requests, trade_matches, trade_negotiations,
trade_agreements, trade_settlements, trade_feedback, trading_analytics -- had never had a
migration, and ``storage.init_db()`` deliberately creates nothing ("Schema management is
Alembic's job"). A fresh deployment therefore came up with ``inter_chain_trades`` and
``island_registry`` and nothing else, and every route touching a trade answered with
``no such table``. The deployed database has all nine only because something ran
``create_all`` against it before that policy was written -- the same accident that left four
of coordinator-api's tables sitting in it.

Migration 002 already names columns in four of the missing tables. Its guard skips tables
that do not exist, so on a fresh database it silently migrated nothing.

Two more gaps found while reconciling head against the models, both in tables 001 did build:

* ``inter_chain_trades`` is missing the five v0.9.0 HTLC columns -- escrow_id,
  settlement_phase, secret_hash, source_timelock, dest_timelock. Added with server defaults
  matching the model's Python-side defaults, so the ALTER is valid on a table with rows.
* 26 of the models' indexes were never created, and 001 creates two that the models do not
  declare: ``idx_inter_chain_trades_source_chain`` and ``idx_inter_chain_trades_dest_chain``
  duplicate ``ix_inter_chain_trades_source_chain`` and ``ix_inter_chain_trades_dest_chain``
  column for column. The models are the source of truth autogenerate compares against, so
  the duplicates are dropped rather than added to the models.

Money columns still declared FLOAT become Numeric(20, 8). 002 converts them only on
non-SQLite, reasoning that the SQLite type is advisory -- which is true of the *stored value*
(SQLite gives both FLOAT and NUMERIC declarations REAL affinity, so neither preserves more
precision than the other) but not of the *schema*. Alembic compares types by default, so
leaving them FLOAT means every future ``--autogenerate`` re-reports the same change forever.
On the deployed database this covers ``inter_chain_trades.price`` plus the nine money columns
in ``trade_agreements``, ``trade_settlements`` and ``trading_analytics``, which ``create_all``
built back when the models said Float. Converted through batch mode, the supported path on
SQLite, and skipped per column where the type is already Numeric.

Every operation is guarded, because this has to be safe to run against the deployed database
that already holds all nine tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The v0.9.0 HTLC fields on inter_chain_trades. The server defaults mirror the models'
# Python-side defaults, so the NOT NULL is satisfiable on a table that already has rows.
_HTLC_COLUMNS: list[sa.Column] = [
    sa.Column("escrow_id", sa.String(), nullable=True),
    sa.Column("settlement_phase", sa.String(), nullable=False, server_default="none"),
    sa.Column("secret_hash", sa.String(), nullable=False, server_default=""),
    sa.Column("source_timelock", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("dest_timelock", sa.Integer(), nullable=False, server_default="0"),
]

# Indexes the models declare on the two tables 001 built, which 001 never created.
_MISSING_INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_inter_chain_trades_dest_chain", "inter_chain_trades", ["dest_chain"]),
    ("ix_inter_chain_trades_sender", "inter_chain_trades", ["sender"]),
    ("ix_inter_chain_trades_settlement_phase", "inter_chain_trades", ["settlement_phase"]),
    ("ix_inter_chain_trades_source_chain", "inter_chain_trades", ["source_chain"]),
    ("ix_inter_chain_trades_status", "inter_chain_trades", ["status"]),
    ("ix_island_registry_status", "island_registry", ["status"]),
]

# 001 creates these; the models do not declare them, and each duplicates an ix_ index above.
_DUPLICATE_INDEXES: list[tuple[str, str, list[str]]] = [
    ("idx_inter_chain_trades_source_chain", "inter_chain_trades", ["source_chain"]),
    ("idx_inter_chain_trades_dest_chain", "inter_chain_trades", ["dest_chain"]),
]

# Every money column in this service, as 002 lists them. 002 converts them to Numeric(20, 8)
# on PostgreSQL and returns early on SQLite; whichever of them already exist as FLOAT get
# converted here so an upgraded database ends up shaped like a fresh one on both backends.
_MONEY_COLUMNS: list[tuple[str, set[str]]] = [
    ("inter_chain_trades", {"price"}),
    ("trade_agreements", {"total_price"}),
    ("trade_settlements", {"total_amount", "platform_fee", "processing_fee", "gas_fee", "net_amount_seller"}),
    ("trading_analytics", {"total_trade_volume", "average_trade_value", "total_platform_fees"}),
]


def upgrade() -> None:
    """Bring the database up to the models.

    Tables first, in foreign-key order: trade_requests, then trading_analytics (no keys),
    then matches -> negotiations -> agreements -> feedback and settlements, each of which
    references the one before it by a non-primary unique column.
    """
    op.create_table(
        "trade_requests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("buyer_agent_id", sa.String(), nullable=False),
        sa.Column(
            "trade_type",
            sa.Enum(
                "AI_POWER",
                "COMPUTE_RESOURCES",
                "DATA_SERVICES",
                "MODEL_SERVICES",
                "INFERENCE_TASKS",
                "TRAINING_TASKS",
                name="tradetype",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("requirements", sa.JSON(), nullable=True),
        sa.Column("specifications", sa.JSON(), nullable=True),
        sa.Column("constraints", sa.JSON(), nullable=True),
        sa.Column("budget_range", sa.JSON(), nullable=True),
        sa.Column("preferred_terms", sa.JSON(), nullable=True),
        sa.Column("negotiation_flexible", sa.Boolean(), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("duration_hours", sa.Integer(), nullable=True),
        sa.Column("urgency_level", sa.String(), nullable=False),
        sa.Column("preferred_regions", sa.JSON(), nullable=True),
        sa.Column("excluded_regions", sa.JSON(), nullable=True),
        sa.Column("service_level_required", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN", "MATCHING", "NEGOTIATING", "AGREED", "SETTLING", "COMPLETED", "CANCELLED", "FAILED", name="tradestatus"
            ),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False),
        sa.Column("negotiation_count", sa.Integer(), nullable=False),
        sa.Column("best_match_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_activity", sa.DateTime(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("trading_meta_data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_trade_requests_buyer_agent_id", "trade_requests", ["buyer_agent_id"], unique=False, if_not_exists=True)
    op.create_index("ix_trade_requests_request_id", "trade_requests", ["request_id"], unique=True, if_not_exists=True)
    op.create_table(
        "trading_analytics",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("period_type", sa.String(), nullable=False),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("total_trades", sa.Integer(), nullable=False),
        sa.Column("completed_trades", sa.Integer(), nullable=False),
        sa.Column("failed_trades", sa.Integer(), nullable=False),
        sa.Column("cancelled_trades", sa.Integer(), nullable=False),
        sa.Column("total_trade_volume", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("average_trade_value", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("total_platform_fees", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("trade_type_distribution", sa.JSON(), nullable=True),
        sa.Column("active_buyers", sa.Integer(), nullable=False),
        sa.Column("active_sellers", sa.Integer(), nullable=False),
        sa.Column("new_agents", sa.Integer(), nullable=False),
        sa.Column("average_matching_time", sa.Float(), nullable=False),
        sa.Column("average_negotiation_time", sa.Float(), nullable=False),
        sa.Column("average_settlement_time", sa.Float(), nullable=False),
        sa.Column("success_rate", sa.Float(), nullable=False),
        sa.Column("regional_distribution", sa.JSON(), nullable=True),
        sa.Column("average_rating", sa.Float(), nullable=False),
        sa.Column("dispute_rate", sa.Float(), nullable=False),
        sa.Column("repeat_trade_rate", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("analytics_data", sa.JSON(), nullable=True),
        sa.Column("trends_data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_table(
        "trade_matches",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("match_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("buyer_agent_id", sa.String(), nullable=False),
        sa.Column("seller_agent_id", sa.String(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("confidence_level", sa.Float(), nullable=False),
        sa.Column("price_compatibility", sa.Float(), nullable=False),
        sa.Column("timing_compatibility", sa.Float(), nullable=False),
        sa.Column("specification_compatibility", sa.Float(), nullable=False),
        sa.Column("reputation_compatibility", sa.Float(), nullable=False),
        sa.Column("geographic_compatibility", sa.Float(), nullable=False),
        sa.Column("seller_offer", sa.JSON(), nullable=True),
        sa.Column("proposed_terms", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN", "MATCHING", "NEGOTIATING", "AGREED", "SETTLING", "COMPLETED", "CANCELLED", "FAILED", name="tradestatus"
            ),
            nullable=False,
        ),
        sa.Column("buyer_response", sa.String(), nullable=True),
        sa.Column("seller_response", sa.String(), nullable=True),
        sa.Column("negotiation_initiated", sa.Boolean(), nullable=False),
        sa.Column("negotiation_initiator", sa.String(), nullable=True),
        sa.Column("initial_terms", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_interaction", sa.DateTime(), nullable=True),
        sa.Column("match_factors", sa.JSON(), nullable=True),
        sa.Column("interaction_history", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["trade_requests.request_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_trade_matches_buyer_agent_id", "trade_matches", ["buyer_agent_id"], unique=False, if_not_exists=True)
    op.create_index("ix_trade_matches_match_id", "trade_matches", ["match_id"], unique=True, if_not_exists=True)
    op.create_index("ix_trade_matches_request_id", "trade_matches", ["request_id"], unique=False, if_not_exists=True)
    op.create_index("ix_trade_matches_seller_agent_id", "trade_matches", ["seller_agent_id"], unique=False, if_not_exists=True)
    op.create_table(
        "trade_negotiations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("negotiation_id", sa.String(), nullable=False),
        sa.Column("match_id", sa.String(), nullable=False),
        sa.Column("buyer_agent_id", sa.String(), nullable=False),
        sa.Column("seller_agent_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "ACTIVE", "ACCEPTED", "REJECTED", "COUNTERED", "EXPIRED", name="negotiationstatus"),
            nullable=False,
        ),
        sa.Column("negotiation_round", sa.Integer(), nullable=False),
        sa.Column("max_rounds", sa.Integer(), nullable=False),
        sa.Column("current_terms", sa.JSON(), nullable=True),
        sa.Column("initial_terms", sa.JSON(), nullable=True),
        sa.Column("final_terms", sa.JSON(), nullable=True),
        sa.Column("price_range", sa.JSON(), nullable=True),
        sa.Column("service_level_agreements", sa.JSON(), nullable=True),
        sa.Column("delivery_terms", sa.JSON(), nullable=True),
        sa.Column("payment_terms", sa.JSON(), nullable=True),
        sa.Column("concession_count", sa.Integer(), nullable=False),
        sa.Column("counter_offer_count", sa.Integer(), nullable=False),
        sa.Column("agreement_score", sa.Float(), nullable=False),
        sa.Column("ai_assisted", sa.Boolean(), nullable=False),
        sa.Column("negotiation_strategy", sa.String(), nullable=False),
        sa.Column("auto_accept_threshold", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_offer_at", sa.DateTime(), nullable=True),
        sa.Column("negotiation_history", sa.JSON(), nullable=True),
        sa.Column("ai_recommendations", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["match_id"],
            ["trade_matches.match_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_trade_negotiations_buyer_agent_id", "trade_negotiations", ["buyer_agent_id"], unique=False, if_not_exists=True
    )
    op.create_index("ix_trade_negotiations_match_id", "trade_negotiations", ["match_id"], unique=False, if_not_exists=True)
    op.create_index(
        "ix_trade_negotiations_negotiation_id", "trade_negotiations", ["negotiation_id"], unique=True, if_not_exists=True
    )
    op.create_index(
        "ix_trade_negotiations_seller_agent_id", "trade_negotiations", ["seller_agent_id"], unique=False, if_not_exists=True
    )
    op.create_table(
        "trade_agreements",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agreement_id", sa.String(), nullable=False),
        sa.Column("negotiation_id", sa.String(), nullable=False),
        sa.Column("buyer_agent_id", sa.String(), nullable=False),
        sa.Column("seller_agent_id", sa.String(), nullable=False),
        sa.Column(
            "trade_type",
            sa.Enum(
                "AI_POWER",
                "COMPUTE_RESOURCES",
                "DATA_SERVICES",
                "MODEL_SERVICES",
                "INFERENCE_TASKS",
                "TRAINING_TASKS",
                name="tradetype",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("agreed_terms", sa.JSON(), nullable=True),
        sa.Column("specifications", sa.JSON(), nullable=True),
        sa.Column("service_level_agreement", sa.JSON(), nullable=True),
        sa.Column("total_price", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("payment_schedule", sa.JSON(), nullable=True),
        sa.Column(
            "settlement_type",
            sa.Enum("IMMEDIATE", "ESCROW", "MILESTONE", "SUBSCRIPTION", name="settlementtype"),
            nullable=False,
        ),
        sa.Column("delivery_timeline", sa.JSON(), nullable=True),
        sa.Column("performance_metrics", sa.JSON(), nullable=True),
        sa.Column("quality_standards", sa.JSON(), nullable=True),
        sa.Column("terms_and_conditions", sa.String(5000), nullable=False),
        sa.Column("compliance_requirements", sa.JSON(), nullable=True),
        sa.Column("dispute_resolution", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN", "MATCHING", "NEGOTIATING", "AGREED", "SETTLING", "COMPLETED", "CANCELLED", "FAILED", name="tradestatus"
            ),
            nullable=False,
        ),
        sa.Column("execution_status", sa.String(), nullable=False),
        sa.Column("completion_percentage", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("signed_at", sa.DateTime(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("agreement_document", sa.JSON(), nullable=True),
        sa.Column("attachments", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["negotiation_id"],
            ["trade_negotiations.negotiation_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_trade_agreements_agreement_id", "trade_agreements", ["agreement_id"], unique=True, if_not_exists=True)
    op.create_index(
        "ix_trade_agreements_buyer_agent_id", "trade_agreements", ["buyer_agent_id"], unique=False, if_not_exists=True
    )
    op.create_index(
        "ix_trade_agreements_negotiation_id", "trade_agreements", ["negotiation_id"], unique=False, if_not_exists=True
    )
    op.create_index(
        "ix_trade_agreements_seller_agent_id", "trade_agreements", ["seller_agent_id"], unique=False, if_not_exists=True
    )
    op.create_table(
        "trade_feedback",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agreement_id", sa.String(), nullable=False),
        sa.Column("reviewer_agent_id", sa.String(), nullable=False),
        sa.Column("reviewed_agent_id", sa.String(), nullable=False),
        sa.Column("reviewer_role", sa.String(), nullable=False),
        sa.Column("overall_rating", sa.Float(), nullable=False),
        sa.Column("communication_rating", sa.Float(), nullable=False),
        sa.Column("performance_rating", sa.Float(), nullable=False),
        sa.Column("timeliness_rating", sa.Float(), nullable=False),
        sa.Column("value_rating", sa.Float(), nullable=False),
        sa.Column("feedback_text", sa.String(1000), nullable=False),
        sa.Column("feedback_tags", sa.JSON(), nullable=True),
        sa.Column("trade_category", sa.String(), nullable=False),
        sa.Column("trade_complexity", sa.String(), nullable=False),
        sa.Column("trade_duration", sa.Integer(), nullable=True),
        sa.Column("verified_trade", sa.Boolean(), nullable=False),
        sa.Column("moderation_status", sa.String(), nullable=False),
        sa.Column("moderator_notes", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("trade_completed_at", sa.DateTime(), nullable=False),
        sa.Column("feedback_context", sa.JSON(), nullable=True),
        sa.Column("performance_metrics", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["agreement_id"],
            ["trade_agreements.agreement_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index("ix_trade_feedback_agreement_id", "trade_feedback", ["agreement_id"], unique=False, if_not_exists=True)
    op.create_index(
        "ix_trade_feedback_reviewed_agent_id", "trade_feedback", ["reviewed_agent_id"], unique=False, if_not_exists=True
    )
    op.create_index(
        "ix_trade_feedback_reviewer_agent_id", "trade_feedback", ["reviewer_agent_id"], unique=False, if_not_exists=True
    )
    op.create_table(
        "trade_settlements",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("settlement_id", sa.String(), nullable=False),
        sa.Column("agreement_id", sa.String(), nullable=False),
        sa.Column("buyer_agent_id", sa.String(), nullable=False),
        sa.Column("seller_agent_id", sa.String(), nullable=False),
        sa.Column(
            "settlement_type",
            sa.Enum("IMMEDIATE", "ESCROW", "MILESTONE", "SUBSCRIPTION", name="settlementtype"),
            nullable=False,
        ),
        sa.Column("total_amount", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("currency", sa.String(), nullable=False),
        sa.Column("payment_status", sa.String(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=True),
        sa.Column("transaction_hash", sa.String(), nullable=True),
        sa.Column("block_number", sa.Integer(), nullable=True),
        sa.Column("escrow_enabled", sa.Boolean(), nullable=False),
        sa.Column("escrow_address", sa.String(), nullable=True),
        sa.Column("escrow_release_conditions", sa.JSON(), nullable=True),
        sa.Column("milestone_payments", sa.JSON(), nullable=True),
        sa.Column("completed_milestones", sa.JSON(), nullable=True),
        sa.Column("platform_fee", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("processing_fee", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("gas_fee", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("net_amount_seller", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN", "MATCHING", "NEGOTIATING", "AGREED", "SETTLING", "COMPLETED", "CANCELLED", "FAILED", name="tradestatus"
            ),
            nullable=False,
        ),
        sa.Column("initiated_at", sa.DateTime(), nullable=False),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("refunded_at", sa.DateTime(), nullable=True),
        sa.Column("dispute_raised", sa.Boolean(), nullable=False),
        sa.Column("dispute_details", sa.JSON(), nullable=True),
        sa.Column("resolution_details", sa.JSON(), nullable=True),
        sa.Column("settlement_data", sa.JSON(), nullable=True),
        sa.Column("audit_trail", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["agreement_id"],
            ["trade_agreements.agreement_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_trade_settlements_agreement_id", "trade_settlements", ["agreement_id"], unique=False, if_not_exists=True
    )
    op.create_index(
        "ix_trade_settlements_buyer_agent_id", "trade_settlements", ["buyer_agent_id"], unique=False, if_not_exists=True
    )
    op.create_index(
        "ix_trade_settlements_seller_agent_id", "trade_settlements", ["seller_agent_id"], unique=False, if_not_exists=True
    )
    op.create_index(
        "ix_trade_settlements_settlement_id", "trade_settlements", ["settlement_id"], unique=True, if_not_exists=True
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` is not SQLite syntax, so the guard is an
    # inspector read rather than `if_not_exists=True`.
    existing = {c["name"] for c in inspector.get_columns("inter_chain_trades")}
    for column in _HTLC_COLUMNS:
        if column.name not in existing:
            op.add_column("inter_chain_trades", column)

    for name, table, columns in _MISSING_INDEXES:
        op.create_index(name, table, columns, unique=False, if_not_exists=True)
    for name, table, _ in _DUPLICATE_INDEXES:
        op.drop_index(name, table_name=table, if_exists=True)

    # Money columns last, and only the ones still declared FLOAT. On a fresh database the
    # seven tables above were just built with Numeric and there is nothing to do; on the
    # deployed one, three of them were built by `create_all` back when the models said Float,
    # and 002 -- which converts them -- returns early on SQLite. So this is the branch that
    # actually runs, and it is what makes an upgraded old database match a fresh one.
    #
    # batch mode: SQLite has no ALTER COLUMN, so each of these is a rebuild-and-copy. It runs
    # after the column and index work above so the rebuild carries the final shape across.
    inspector = sa.inspect(bind)  # re-read: the tables above did not exist when the first ran
    existing_tables = set(inspector.get_table_names())
    for table, columns in _MONEY_COLUMNS:
        if table not in existing_tables:
            continue
        stale = [
            # `not isinstance(type, sa.Numeric)` is the obvious test and it is wrong: sa.Float
            # subclasses sa.Numeric, so a FLOAT column passes it and every conversion is
            # skipped. Still-a-Float is the condition that means "not converted yet".
            c["name"]
            for c in inspector.get_columns(table)
            if c["name"] in columns and isinstance(c["type"], sa.Float)
        ]
        if not stale:
            continue
        with op.batch_alter_table(table) as batch:
            for name in stale:
                batch.alter_column(name, existing_type=sa.FLOAT(), type_=sa.Numeric(20, 8), existing_nullable=False)


def downgrade() -> None:
    """Reverse 003.

    The seven tables and their indexes go together -- dropping a table drops its indexes --
    so only the two 001 tables need unwinding by hand.
    """
    # Only inter_chain_trades needs its money column put back; the other three tables in
    # _MONEY_COLUMNS are dropped whole at the end of this function.
    with op.batch_alter_table("inter_chain_trades") as batch:
        batch.alter_column("price", existing_type=sa.Numeric(20, 8), type_=sa.FLOAT(), existing_nullable=False)

    for name, table, columns in _DUPLICATE_INDEXES:
        op.create_index(name, table, columns, if_not_exists=True)
    for name, table, _ in _MISSING_INDEXES:
        op.drop_index(name, table_name=table, if_exists=True)

    with op.batch_alter_table("inter_chain_trades") as batch:
        for column in reversed(_HTLC_COLUMNS):
            batch.drop_column(column.name)

    for table in (
        "trade_settlements",
        "trade_feedback",
        "trade_agreements",
        "trade_negotiations",
        "trade_matches",
        "trading_analytics",
        "trade_requests",
    ):
        op.drop_table(table)
