"""b4_exact_monetary_semantics

Migrate remaining monetary columns in coordinator financial, marketplace,
staking, and cross-chain models from Float to Numeric so all price, balance,
fee, and gas values keep exact decimal semantics.

Affected tables:
- agent_wallets (balance, spending_limit, total_spent)
- chain_transaction (amount)
- gpu_registry (price_per_hour)
- gpu_booking (total_cost)
- wallets (balance)
- user_transaction / transactions (amount, fee)
- bridge_request (amount, bridge_fee, total_amount, exchange_rate)
- bridge_transaction (gas_price, transaction_cost)
- bridge_dispute (refund_amount, compensation_amount, penalty_amount)
- validator_reward (reward_amount)
- chain_config (max_gas_price, validator_threshold)
- wallet_transaction (value, gas_price)
- token_balance (balance)

Revision ID: e9cf23ae4640
Revises: 021f508dbce7
Create Date: 2026-07-21 09:43:44.665467+00:00

"""

from collections.abc import Sequence

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e9cf23ae4640"
down_revision: str | Sequence[str] | None = "021f508dbce7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


# (table, column, new_type, nullable)
_COLUMNS: list[tuple[str, str, sa.Numeric, bool]] = [
    # Agent wallet financial columns (coordinator agent identity)
    ("agent_wallets", "balance", sa.Numeric(20, 8), False),
    ("agent_wallets", "spending_limit", sa.Numeric(20, 8), False),
    ("agent_wallets", "total_spent", sa.Numeric(20, 8), False),
    # Cross-chain transaction amount
    ("chain_transaction", "amount", sa.Numeric(20, 8), False),
    # GPU marketplace
    ("gpu_registry", "price_per_hour", sa.Numeric(20, 8), False),
    ("gpu_bookings", "total_cost", sa.Numeric(20, 8), False),
    # User wallet/transaction balances
    ("wallets", "balance", sa.Numeric(20, 8), False),
    ("transactions", "amount", sa.Numeric(20, 8), False),
    ("transactions", "fee", sa.Numeric(20, 8), False),
    # Wallet transaction value (already exact in model, reconcile stale DBs)
    ("wallet_transaction", "value", sa.Numeric(20, 8), False),
    ("wallet_transaction", "gas_price", sa.Numeric(20, 8), True),
    ("token_balance", "balance", sa.Numeric(20, 8), False),
    # Bridge request monetary fields
    ("bridge_request", "amount", sa.Numeric(), False),
    ("bridge_request", "bridge_fee", sa.Numeric(), False),
    ("bridge_request", "total_amount", sa.Numeric(), False),
    ("bridge_request", "exchange_rate", sa.Numeric(), False),
    # Bridge transaction gas/cost
    ("bridge_transaction", "gas_price", sa.Numeric(20, 8), True),
    ("bridge_transaction", "transaction_cost", sa.Numeric(20, 8), True),
    # Bridge dispute amounts
    ("bridge_dispute", "refund_amount", sa.Numeric(20, 8), True),
    ("bridge_dispute", "compensation_amount", sa.Numeric(20, 8), True),
    ("bridge_dispute", "penalty_amount", sa.Numeric(20, 8), True),
    # Validator reward
    ("validator_reward", "reward_amount", sa.Numeric(20, 8), False),
    # Chain config
    ("chain_config", "max_gas_price", sa.Numeric(), False),
    ("chain_config", "validator_threshold", sa.Numeric(), False),
    # Supported bridge tokens
    ("supported_token", "bridge_limit", sa.Numeric(), False),
    ("supported_token", "fee_percentage", sa.Numeric(), False),
    ("supported_token", "min_amount", sa.Numeric(), False),
    ("supported_token", "max_amount", sa.Numeric(), False),
    # Staking
    ("agent_stakes", "amount", sa.Numeric(), False),
    ("agent_stakes", "accumulated_rewards", sa.Numeric(), False),
    ("agent_stakes", "current_apy", sa.Numeric(), False),
    ("agent_stakes", "performance_multiplier", sa.Numeric(), False),
    ("agent_stakes", "early_unbond_penalty", sa.Numeric(), False),
    ("agent_stakes", "lock_bonus_multiplier", sa.Numeric(), False),
    ("agent_metrics", "total_staked", sa.Numeric(), False),
    ("agent_metrics", "total_rewards_distributed", sa.Numeric(), False),
    ("agent_metrics", "average_accuracy", sa.Numeric(), False),
    ("agent_metrics", "success_rate", sa.Numeric(), False),
    ("agent_metrics", "tier_score", sa.Numeric(), False),
    ("agent_metrics", "reputation_score", sa.Numeric(), False),
    ("agent_metrics", "average_response_time", sa.Numeric(), True),
    ("agent_metrics", "total_compute_time", sa.Numeric(), True),
    ("agent_metrics", "energy_efficiency_score", sa.Numeric(), True),
    ("staking_pools", "total_staked", sa.Numeric(), False),
    ("staking_pools", "total_rewards", sa.Numeric(), False),
    ("staking_pools", "pool_apy", sa.Numeric(), False),
    ("staking_pools", "min_stake_amount", sa.Numeric(), False),
    ("staking_pools", "max_stake_amount", sa.Numeric(), False),
    ("staking_pools", "pool_performance_score", sa.Numeric(), False),
    ("staking_pools", "volatility_score", sa.Numeric(), False),
    # Job marketplace/settlement amounts
    ("job", "payment_amount", sa.Numeric(36, 18), True),
    ("job", "cross_chain_amount", sa.Numeric(36, 18), True),
]


def _alter_columns(bind: sa.engine.Connection) -> None:
    """Alter each monetary column to the target Numeric type."""
    for table, column, new_type, nullable in _COLUMNS:
        if not _table_exists(bind, table):
            continue
        existing_type = sa.Float()
        if bind.dialect.name == "sqlite" and not context.is_offline_mode():
            with op.batch_alter_table(table, recreate="always") as batch_op:
                batch_op.alter_column(
                    column_name=column,
                    type_=new_type,
                    existing_type=existing_type,
                    nullable=nullable,
                )
        else:
            op.alter_column(
                table_name=table,
                column_name=column,
                type_=new_type,
                existing_type=existing_type,
                nullable=nullable,
            )


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    _alter_columns(bind)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    for table, column, _new_type, nullable in _COLUMNS:
        if not _table_exists(bind, table):
            continue
        if bind.dialect.name == "sqlite" and not context.is_offline_mode():
            with op.batch_alter_table(table, recreate="always") as batch_op:
                batch_op.alter_column(
                    column_name=column,
                    type_=sa.Float(),
                    existing_type=_new_type,
                    nullable=nullable,
                )
        else:
            op.alter_column(
                table_name=table,
                column_name=column,
                type_=sa.Float(),
                existing_type=_new_type,
                nullable=nullable,
            )
