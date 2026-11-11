"""drop dead tables flagged by the #1603 census (#1840)

The #1603 dead-table inventory (docs/ops/dead-table-inventory-1603.md)
flagged ~60 coordinator tables as dead-on-arrival or write-only mirrors:
models existed and 001_initial_migration created them, but nothing in
apps/*/src ever selected, inserted or updated them. Live-DB census
(pg_stat_user_tables, all 5 nodes) confirmed every flagged table empty.

This revision drops them so fresh deploys and existing databases converge
through the migration chain (coordinator-api runs ``alembic upgrade head``
in ExecStartPre). ``DROP TABLE IF EXISTS`` keeps it a no-op for tables
that were model-only and never migrated (confidential_*, portfolio_alert,
trading_rule, market_condition, agent_portfolio, risk_metrics,
portfolio_strategy, training_round, local_model_update,
agent_memory_node, pricing_summary_view, market_heatmap_view).

Held back per #1840: the ``trade_settlements`` orphan pair (design
decision still open) and pool-hub dormant tables.

Revision ID: f6a7b8c9d0e1
Revises: i3j4k5l6m7n8
Create Date: 2026-11-11

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes  # noqa: F401  (AutoString resolution parity with 001)

# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "i3j4k5l6m7n8"
branch_labels = None
depends_on = None

_DEAD_TABLES = [
    # models/confidential.py — confidential-tx feature never wired
    "confidential_transactions",
    "participant_keys",
    "confidential_access_logs",
    "key_rotation_logs",
    "audit_authorizations",
    # reputation domain dead candidates (+ near-dead metrics/events)
    "trust_score_calculations",
    "agent_economic_profiles",
    "reputation_level_thresholds",
    "reputation_metrics",
    "cross_chain_reputation_events",
    # portfolio domain — entire agent_portfolio cluster
    "portfolio_strategy",
    "agent_portfolio",
    "portfolio_asset",
    "portfolio_trade",
    "risk_metrics",
    "performance_metrics",
    "rebalance_history",
    "portfolio_alert",
    "strategy_signal",
    "portfolio_snapshot",
    "trading_rule",
    "market_condition",
    # cross_chain bridge cluster (bridge_request/chain_config/validator/
    # merkle_proof/bridge_liquidity_pool stay — they have live readers)
    "supported_token",
    "bridge_transaction",
    "bridge_dispute",
    "bridge_statistics",
    "bridge_alert",
    "bridge_configuration",
    "bridge_snapshot",
    "validator_reward",
    # certification dead candidates
    "certification_requirements",
    "certification_audits",
    # analytics dead candidates
    "analytics_reports",
    "data_collection_jobs",
    "user_preferences",
    # multitenant scaffold dead candidates (tenants/tenant_quotas/
    # usage_records/invoices stay)
    "tenant_users",
    "tenant_api_keys",
    "tenant_audit_logs",
    "tenant_metrics",
    # dao_governance dead candidates (dao_vote/dao_treasury stay)
    "dao_member",
    "dao_proposal",
    "treasury_allocation",
    # community dead candidates
    "agent_solutions",
    "innovation_labs",
    "community_posts",
    # federated learning cluster
    "federated_learning_session",
    "training_participant",
    "training_round",
    "local_model_update",
    # misc singletons
    "agent_memory_node",
    "user_sessions",
    # trading *_view models + dead mirrors
    "pricing_summary_view",
    "market_heatmap_view",
    "trade_feedback",
    "trading_analytics",
    # global_marketplace_* mirror cluster + shared marketplace_bid
    "global_marketplace_offers",
    "global_marketplace_transactions",
    "global_marketplace_configs",
    "global_marketplace_analytics",
    "global_marketplace_governance",
    "marketplace_regions",
    "marketplace_bid",
]


def upgrade() -> None:
    # CASCADE on Postgres: dead tables FK each other and the kept-but-dead
    # dao_vote still declares FKs to dao_member/dao_proposal — dropping the
    # parents must remove those constraints or Postgres refuses the drop.
    # SQLite has no CASCADE clause and no such enforcement; emit plain DROP.
    cascade = " CASCADE" if op.get_bind().dialect.name == "postgresql" else ""
    for table in _DEAD_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table}"{cascade}')
    _strip_dao_vote_fks()


def _strip_dao_vote_fks() -> None:
    """Rebuild ``dao_vote`` without its FKs to ``dao_member``/``dao_proposal``.

    The kept ``Vote`` model no longer declares those FKs (their targets are
    dropped above). Postgres ``CASCADE`` already removes the dependent
    constraints, but SQLite keeps the FK clauses in ``dao_vote``'s stored
    DDL — a rebuild makes both dialects converge to the model schema.
    """
    op.create_table(
        "dao_vote_new",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("proposal_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("member_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("support", sa.Boolean(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("tx_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        'INSERT INTO "dao_vote_new" ("id", "proposal_id", "member_id", "support", '
        '"weight", "tx_hash", "created_at") SELECT "id", "proposal_id", "member_id", '
        '"support", "weight", "tx_hash", "created_at" FROM "dao_vote"'
    )
    op.execute('DROP TABLE "dao_vote"')
    op.execute('ALTER TABLE "dao_vote_new" RENAME TO "dao_vote"')
    op.execute('CREATE INDEX IF NOT EXISTS "ix_dao_vote_member_id" ON "dao_vote" ("member_id")')
    op.execute('CREATE INDEX IF NOT EXISTS "ix_dao_vote_proposal_id" ON "dao_vote" ("proposal_id")')


def downgrade() -> None:
    # Dead tables carried no live data (fleet census: all empty); there is
    # nothing to restore. Recreating 60 empty shells would only re-add the
    # dead schema this revision removes.
    pass
