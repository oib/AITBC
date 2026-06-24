"""Add query performance indexes to high-traffic columns

Adds single-column indexes on status/created_at columns that are frequently
filtered or ordered on at the SQL level (identified by auditing the
storage/repository query patterns), plus the previously commented-out
composite indexes on the agent_identity tables.

These mirror the ``index=True`` declarations added to the SQLModel domain
classes. ``create_all`` applies them to fresh databases; this migration
applies them to already-provisioned databases. ``if_not_exists`` keeps the
migration idempotent so it is safe to run on DBs that were created fresh
after the model changes.

Revision ID: add_query_performance_indexes
Revises: add_developer_platform
Create Date: 2026-06-24 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_query_performance_indexes"
down_revision = "add_developer_platform"
branch_labels = None
depends_on = None


# (index_name, table_name, [columns]) for single-column indexes.
# Index names follow SQLAlchemy's default ``ix_<table>_<column>`` convention so
# they match what ``SQLModel.metadata.create_all`` would generate.
_SINGLE_COLUMN_INDEXES: list[tuple[str, str, list[str]]] = [
    # agent coordination
    ("ix_agent_executions_status", "agent_executions", ["status"]),
    ("ix_agent_step_executions_status", "agent_step_executions", ["status"]),
    # bounty
    ("ix_bounties_status", "bounties", ["status"]),
    ("ix_bounties_creation_time", "bounties", ["creation_time"]),
    ("ix_bounty_submissions_status", "bounty_submissions", ["status"]),
    ("ix_bounty_submissions_submission_time", "bounty_submissions", ["submission_time"]),
    ("ix_agent_stakes_status", "agent_stakes", ["status"]),
    # trading
    ("ix_trade_requests_status", "trade_requests", ["status"]),
    ("ix_trade_requests_created_at", "trade_requests", ["created_at"]),
    ("ix_trade_matches_status", "trade_matches", ["status"]),
    ("ix_trade_negotiations_status", "trade_negotiations", ["status"]),
    ("ix_trade_negotiations_created_at", "trade_negotiations", ["created_at"]),
    # analytics
    ("ix_market_metrics_recorded_at", "market_metrics", ["recorded_at"]),
    ("ix_market_insights_status", "market_insights", ["status"]),
    ("ix_market_insights_created_at", "market_insights", ["created_at"]),
    ("ix_analytics_reports_status", "analytics_reports", ["status"]),
    ("ix_dashboard_configs_status", "dashboard_configs", ["status"]),
    ("ix_data_collection_jobs_status", "data_collection_jobs", ["status"]),
    ("ix_alert_rules_status", "alert_rules", ["status"]),
    ("ix_analytics_alerts_status", "analytics_alerts", ["status"]),
    ("ix_analytics_alerts_created_at", "analytics_alerts", ["created_at"]),
    # certification
    ("ix_agent_certifications_status", "agent_certifications", ["status"]),
    ("ix_verification_records_status", "verification_records", ["status"]),
    ("ix_partnership_programs_status", "partnership_programs", ["status"]),
    ("ix_partnership_programs_created_at", "partnership_programs", ["created_at"]),
    ("ix_agent_partnerships_status", "agent_partnerships", ["status"]),
    # rewards
    ("ix_reward_distributions_status", "reward_distributions", ["status"]),
    ("ix_reward_distributions_created_at", "reward_distributions", ["created_at"]),
    ("ix_reward_milestones_created_at", "reward_milestones", ["created_at"]),
    # reputation / community
    ("ix_community_feedback_moderation_status", "community_feedback", ["moderation_status"]),
    ("ix_community_feedback_created_at", "community_feedback", ["created_at"]),
    ("ix_agent_solutions_status", "agent_solutions", ["status"]),
    ("ix_community_posts_created_at", "community_posts", ["created_at"]),
    # developer platform
    ("ix_bounty_task_created_at", "bounty_task", ["created_at"]),
    # agent identity
    ("ix_agent_identities_status", "agent_identities", ["status"]),
]

# Composite indexes on the agent_identity tables (previously commented out in
# the domain models and now enabled).
_COMPOSITE_INDEXES: list[tuple[str, str, list[str]]] = [
    ("idx_cross_chain_agent_chain", "cross_chain_mappings", ["agent_id", "chain_id"]),
    ("idx_cross_chain_address", "cross_chain_mappings", ["chain_address"]),
    ("idx_cross_chain_verified", "cross_chain_mappings", ["is_verified"]),
    ("idx_identity_verify_agent_chain", "identity_verifications", ["agent_id", "chain_id"]),
    ("idx_identity_verify_verifier", "identity_verifications", ["verifier_address"]),
    ("idx_identity_verify_hash", "identity_verifications", ["proof_hash"]),
    ("idx_identity_verify_result", "identity_verifications", ["verification_result"]),
    ("idx_identity_verify_expires", "identity_verifications", ["expires_at"]),
    ("idx_agent_wallet_agent_chain", "agent_wallets", ["agent_id", "chain_id"]),
    ("idx_agent_wallet_address", "agent_wallets", ["chain_address"]),
    ("idx_agent_wallet_active", "agent_wallets", ["is_active"]),
]


def upgrade() -> None:
    """Create the missing query performance indexes."""
    for index_name, table_name, columns in _SINGLE_COLUMN_INDEXES:
        op.create_index(index_name, table_name, columns, if_not_exists=True)
    for index_name, table_name, columns in _COMPOSITE_INDEXES:
        op.create_index(index_name, table_name, columns, if_not_exists=True)


def downgrade() -> None:
    """Drop the query performance indexes."""
    for index_name, _table_name, _columns in _COMPOSITE_INDEXES:
        op.drop_index(index_name, table_name=_table_name)
    for index_name, _table_name, _columns in _SINGLE_COLUMN_INDEXES:
        op.drop_index(index_name, table_name=_table_name)
