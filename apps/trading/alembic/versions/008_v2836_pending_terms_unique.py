"""unique pending-terms index on inter_chain_trades

Revision ID: 008_v2836_pending_terms_unique
Revises: 007
Create Date: 2026-11-24 00:00:00.000000+00:00

#2836: create_trade dedup was check-then-insert with no constraint — two
concurrent identical creates could both insert duplicate pending trades.
This adds a partial unique index on the natural term set scoped to
status='pending' (the same terms may recur once the trade leaves pending).
offer_id is nullable and NULLs are distinct in unique indexes, so the index
uses COALESCE(offer_id, '') — matching the service's ''→NULL normalization.

Existing duplicate pending rows would make CREATE UNIQUE INDEX fail, so the
upgrade first cancels duplicates deterministically: per term set the
earliest-created row survives, later duplicates become 'cancelled'. This is
a deliberate data repair — duplicate pending trades are exactly the defect
being fixed, and a loud migration failure would block every deploy instead.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "008_v2836_pending_terms_unique"
down_revision = "007_v1840_dead_table_drop"
branch_labels = None
depends_on = None

_INDEX_NAME = "uq_inter_chain_trades_pending_terms"

# Cancel every pending row except the earliest-created per term set. Window
# functions + UPDATE...WHERE...IN work on both SQLite (>=3.25) and Postgres.
_DEDUP_SQL = """
WITH ranked AS (
    SELECT trade_id,
           ROW_NUMBER() OVER (
               PARTITION BY source_chain, dest_chain, sender, recipient,
                            amount, COALESCE(offer_id, ''), price, quantity
               ORDER BY created_at, trade_id
           ) AS rn
    FROM inter_chain_trades
    WHERE status = 'pending'
)
UPDATE inter_chain_trades
SET status = 'cancelled', updated_at = :now
WHERE trade_id IN (SELECT trade_id FROM ranked WHERE rn > 1)
"""

# Partial unique index — identical syntax on SQLite and Postgres.
_CREATE_INDEX_SQL = f"""
CREATE UNIQUE INDEX IF NOT EXISTS {_INDEX_NAME}
ON inter_chain_trades (
    source_chain, dest_chain, sender, recipient, amount,
    COALESCE(offer_id, ''), price, quantity
)
WHERE status = 'pending'
"""

_DROP_INDEX_SQL = f"DROP INDEX IF EXISTS {_INDEX_NAME}"


def upgrade() -> None:
    op.get_bind().execute(sa.text(_DEDUP_SQL), {"now": datetime.now(UTC).replace(tzinfo=None)})
    op.execute(_CREATE_INDEX_SQL)


def downgrade() -> None:
    op.execute(_DROP_INDEX_SQL)
