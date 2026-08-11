"""v23_money_columns_to_numeric

Migrate the last Float money columns in coordinator-api to Numeric(20, 8).

This finishes what ``migrate_wallet_to_numeric`` ... ``e9cf23ae4640`` started. Those
passes converted the columns anyone was looking at -- wallets, transactions, marketplace
offers, bridge requests. The 102 columns here are the ones a hand-maintained lint
allowlist never covered, found once ``scripts/lint/no_float_money.py`` was rewritten to
walk every tracked file by AST instead of grepping thirteen paths for ``float(``.

Nothing here is a new column or a new table; every one already exists as Float and is
already read and written as money by the code above it. What changes is that
``0.1 + 0.2`` stops being ``0.30000000000000004`` in a fee, a payout or a balance.

Two properties this migration relies on, both inherited from the earlier ones in this
series and both load-bearing:

* ``_table_exists`` -- coordinator-api creates its schema with
  ``SQLModel.metadata.create_all``, so which tables a given database actually has depends
  on when it was created. Skipping absent tables is what lets this run against all of them.
* ``batch_alter_table(recreate="always")`` on SQLite -- SQLite cannot ``ALTER COLUMN``,
  so the table is rebuilt. On PostgreSQL (which is what the deployed coordinator uses)
  a plain ``ALTER`` suffices and preserves the data.

The downgrade is exact in the direction that matters: Float -> Numeric never loses
information, so ``upgrade`` is lossless. ``downgrade`` is not -- it puts the values back
into binary floating point, which is the defect. It exists so the revision is reversible,
not because reversing it is safe.

Revision ID: c7d1f4a9e230
Revises: 1a7d8e9b0c2f
Create Date: 2026-08-11 11:20:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "c7d1f4a9e230"
down_revision: str | Sequence[str] | None = "1a7d8e9b0c2f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(20, 8)


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table_name: str, column: str) -> bool:
    if context.is_offline_mode():
        return True
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table_name))


# (table, column, nullable)
_COLUMNS: list[tuple[str, str, bool]] = [
    # agent_economic_profiles (reputation)
    ("agent_economic_profiles", "daily_earnings", False),
    ("agent_economic_profiles", "monthly_earnings", False),
    ("agent_economic_profiles", "weekly_earnings", False),
    ("agent_economic_profiles", "yearly_earnings", False),
    # agent_executions (agent)
    ("agent_executions", "total_cost", False),
    # agent_marketplace (agent)
    ("agent_marketplace", "execution_price", False),
    ("agent_marketplace", "subscription_price", False),
    # agent_partnerships (certification)
    ("agent_partnerships", "pending_payments", False),
    ("agent_partnerships", "total_earnings", False),
    # agent_performance_profiles (agent_performance)
    ("agent_performance_profiles", "cost_per_task", False),
    # agent_reputation (reputation)
    ("agent_reputation", "total_earnings", False),
    # agent_solutions (community)
    ("agent_solutions", "price_amount", False),
    # ai_agent_workflows (agent)
    ("ai_agent_workflows", "max_cost_budget", False),
    # arbitrage_opportunity (amm)
    ("arbitrage_opportunity", "actual_profit", True),
    ("arbitrage_opportunity", "gas_cost_estimate", False),
    ("arbitrage_opportunity", "net_profit", False),
    ("arbitrage_opportunity", "potential_profit", False),
    ("arbitrage_opportunity", "price_1", False),
    ("arbitrage_opportunity", "price_2", False),
    ("arbitrage_opportunity", "required_amount", False),
    # atomic_swap_order (atomic_swap)
    ("atomic_swap_order", "source_amount", False),
    ("atomic_swap_order", "target_amount", False),
    # bounty_stats (bounty)
    ("bounty_stats", "average_reward", False),
    ("bounty_stats", "total_fees_collected", False),
    ("bounty_stats", "total_rewards_paid", False),
    ("bounty_stats", "total_value_locked", False),
    # bounty_task (developer_platform)
    ("bounty_task", "reward_amount", False),
    # bridge_snapshot (cross_chain_bridge)
    ("bridge_snapshot", "total_fees_24h", False),
    # bridge_statistics (cross_chain_bridge)
    ("bridge_statistics", "total_fees", False),
    # consumer_gpu_profiles (gpu_models)
    ("consumer_gpu_profiles", "market_price_usd", True),
    # dao_member (dao_governance)
    ("dao_member", "staked_amount", False),
    # dao_treasury (governance)
    ("dao_treasury", "allocated_funds", False),
    ("dao_treasury", "total_balance", False),
    # developer_profile (developer_platform)
    ("developer_profile", "total_earned_aitbc", False),
    # developer_profiles (community)
    ("developer_profiles", "total_earnings", False),
    # ecosystem_metrics (ecosystem)
    ("ecosystem_metrics", "average_bounty_reward", False),
    ("ecosystem_metrics", "dao_revenue", False),
    ("ecosystem_metrics", "developer_earnings_average", False),
    ("ecosystem_metrics", "developer_earnings_total", False),
    ("ecosystem_metrics", "staking_rewards_total", False),
    ("ecosystem_metrics", "treasury_balance", False),
    ("ecosystem_metrics", "treasury_inflow", False),
    ("ecosystem_metrics", "treasury_outflow", False),
    # federated_learning_session (federated_learning)
    ("federated_learning_session", "reward_pool_amount", False),
    # fee_claim (amm)
    ("fee_claim", "fee_amount", False),
    # global_marketplace_analytics (global_marketplace)
    ("global_marketplace_analytics", "average_price", False),
    # incentive_program (amm)
    ("incentive_program", "daily_reward_amount", False),
    ("incentive_program", "remaining_reward_amount", False),
    ("incentive_program", "total_reward_amount", False),
    # liquidity_pool (amm)
    ("liquidity_pool", "fees_24h", False),
    # liquidity_position (amm)
    ("liquidity_position", "current_amount_a", False),
    ("liquidity_position", "current_amount_b", False),
    ("liquidity_position", "deposit_amount_a", False),
    ("liquidity_position", "deposit_amount_b", False),
    ("liquidity_position", "fees_earned", False),
    ("liquidity_position", "liquidity_amount", False),
    ("liquidity_position", "unrealized_pnl", False),
    # liquidity_reward (amm)
    ("liquidity_reward", "reward_amount", False),
    # meta_learning_models (agent_performance)
    ("meta_learning_models", "computational_cost", True),
    # performance_optimizations (agent_performance)
    ("performance_optimizations", "baseline_cost", False),
    ("performance_optimizations", "optimized_cost", False),
    # pool_metrics (amm)
    ("pool_metrics", "total_fees_24h", False),
    # pool_snapshot (amm)
    ("pool_snapshot", "fees_24h", False),
    ("pool_snapshot", "price_a_to_b", False),
    ("pool_snapshot", "price_b_to_a", False),
    # portfolio_asset (agent_portfolio)
    ("portfolio_asset", "average_cost", False),
    ("portfolio_asset", "balance", False),
    ("portfolio_asset", "unrealized_pnl", False),
    # portfolio_snapshot (agent_portfolio)
    ("portfolio_snapshot", "cash_balance", False),
    # portfolio_trade (agent_portfolio)
    ("portfolio_trade", "buy_amount", False),
    ("portfolio_trade", "fee_amount", False),
    ("portfolio_trade", "price", False),
    ("portfolio_trade", "sell_amount", False),
    # price_history (gpu_marketplace)
    ("price_history", "price", False),
    # provider_bond (provider_bond)
    ("provider_bond", "amount", False),
    ("provider_bond", "required_amount", False),
    # rebalance_history (agent_portfolio)
    ("rebalance_history", "rebalance_cost", False),
    # reward_analytics (rewards)
    ("reward_analytics", "average_reward_per_agent", False),
    ("reward_analytics", "bronze_rewards", False),
    ("reward_analytics", "community_rewards", False),
    ("reward_analytics", "diamond_rewards", False),
    ("reward_analytics", "gold_rewards", False),
    ("reward_analytics", "loyalty_rewards", False),
    ("reward_analytics", "milestone_rewards", False),
    ("reward_analytics", "performance_rewards", False),
    ("reward_analytics", "platinum_rewards", False),
    ("reward_analytics", "referral_rewards", False),
    ("reward_analytics", "silver_rewards", False),
    ("reward_analytics", "special_rewards", False),
    ("reward_analytics", "total_rewards_distributed", False),
    # reward_milestones (rewards)
    ("reward_milestones", "reward_amount", False),
    # strategy_signal (agent_portfolio)
    ("strategy_signal", "price_target", False),
    # swap_transaction (amm)
    ("swap_transaction", "amount_in", False),
    ("swap_transaction", "amount_out", False),
    ("swap_transaction", "fee_amount", False),
    ("swap_transaction", "gas_price", True),
    ("swap_transaction", "price", False),
    # training_participant (federated_learning)
    ("training_participant", "earned_reward", False),
    # treasury_allocation (dao_governance)
    ("treasury_allocation", "amount", False),
    # trend_data (gpu_marketplace)
    ("trend_data", "avg_price", False),
    # user_profiles (gpu_marketplace)
    ("user_profiles", "price_range_max", False),
    ("user_profiles", "price_range_min", False),
]


def _convert(to_type: sa.types.TypeEngine, from_type: sa.types.TypeEngine) -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite" and not context.is_offline_mode()
    for table, column, nullable in _COLUMNS:
        if not _table_exists(bind, table) or not _column_exists(bind, table, column):
            continue
        if sqlite:
            with op.batch_alter_table(table, recreate="always") as batch_op:
                batch_op.alter_column(
                    column_name=column,
                    type_=to_type,
                    existing_type=from_type,
                    nullable=nullable,
                )
        else:
            extra = {}
            if to_type is MONEY:
                # PostgreSQL will cast double precision -> numeric implicitly, but saying
                # so keeps the statement valid if the column is ever something else.
                extra["postgresql_using"] = f"{column}::numeric(20,8)"
            op.alter_column(
                table_name=table,
                column_name=column,
                type_=to_type,
                existing_type=from_type,
                nullable=nullable,
                **extra,
            )


def upgrade() -> None:
    _convert(MONEY, sa.Float())


def downgrade() -> None:
    _convert(sa.Float(), MONEY)
