"""v0.26.x money/voting columns Float -> Numeric(20, 8)

001 created every Decimal-backed column as ``sa.Float()`` —
``DOUBLE PRECISION`` on PostgreSQL — while the models have declared
``Column(Numeric(20, 8))`` since the V23 money migration. Money and
voting power must stay exact decimal, never binary float; the same
``init_db``-never-alters gap as the other services left the drift
standing until the first Alembic revision that looks.

``proposals.passing_threshold`` stays ``Float``: the model declares it
``float`` (a ratio, not money), so converting it would create drift in
the other direction. ``dao_treasury.asset_breakdown`` is JSON, likewise
untouched.

Batch mode with ``recreate="always"`` on SQLite (no ``ALTER COLUMN``);
native ``ALTER COLUMN`` on PostgreSQL. Columns already ``Numeric`` are
skipped so re-runs are cheap. Like the pool-hub conversion, an SQLite
rebuild does not carry separately-created indexes, so they are restored
afterwards.

Revision ID: 004
Revises: 003
Create Date: 2026-10-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | Sequence[str] | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(20, 8)

# (table, [columns]) — every column the models declare as Numeric(20, 8)
# but 001 created as Float. passing_threshold (proposals) is deliberately
# absent: the model keeps it float.
_COLUMNS: dict[str, list[str]] = {
    "governance_profiles": ["voting_power", "delegated_power"],
    "proposals": [
        "quorum_required",
        "yes_votes",
        "no_votes",
        "votes_for",
        "votes_against",
        "votes_abstain",
    ],
    "votes": [
        "voting_power_used",
        "power_at_snapshot",
        "delegated_power_at_snapshot",
        "voting_power",
        "vote_weight",
    ],
    "delegations": ["voting_power"],
    "governance_tokens": [
        "token_balance",
        "staked_tokens",
        "voting_power",
        "rewards_claimed",
        "rewards_pending",
    ],
    "token_stakes": ["amount_staked", "rewards_earned"],
    "dao_treasury": ["total_balance", "allocated_funds"],
    "transparency_reports": [
        "total_voting_power_participated",
        "treasury_inflow",
        "treasury_outflow",
    ],
}


def _convert(to_type: sa.types.TypeEngine, from_type: sa.types.TypeEngine) -> None:
    bind = op.get_bind()
    sqlite = bind.dialect.name == "sqlite"
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table, columns in _COLUMNS.items():
        if table not in existing_tables:
            continue
        # `not isinstance(type, sa.Float)` is the obvious "needs converting"
        # test and it is wrong in one direction: sa.Float subclasses
        # sa.Numeric, so a FLOAT column also reads as Numeric. Still-a-Float
        # is the upgrade condition; already-not-Float the downgrade one.
        stale = [
            c["name"]
            for c in inspector.get_columns(table)
            if c["name"] in columns and isinstance(c["type"], sa.Float) == (not isinstance(to_type, sa.Float))
        ]
        if not stale:
            continue
        indexes = inspector.get_indexes(table) if sqlite else []
        with op.batch_alter_table(table, recreate="always" if sqlite else "auto") as batch_op:
            for name in stale:
                batch_op.alter_column(name, existing_type=from_type, type_=to_type, existing_nullable=False)
        if sqlite:
            surviving = {i["name"] for i in sa.inspect(bind).get_indexes(table)}
            for index in indexes:
                if index["name"] not in surviving:
                    op.create_index(
                        index["name"],
                        table,
                        index["column_names"],
                        unique=index["unique"],
                        if_not_exists=True,
                    )


def upgrade() -> None:
    _convert(MONEY, sa.Float())


def downgrade() -> None:
    _convert(sa.Float(), MONEY)
