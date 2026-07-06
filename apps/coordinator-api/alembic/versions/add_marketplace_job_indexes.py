"""Add missing indexes on MarketplaceOffer.status, MarketplaceBid.status, and Job.state

These columns are frequently filtered in queries (e.g. `WHERE status = 'available'`,
`WHERE state = 'QUEUED'`) but had no index, causing full table scans.

Indexes are created with ``if_not_exists=True`` so the migration is safe to run
on databases that already have the indexes (e.g. fresh DBs created after the
model update).

Revision ID: add_marketplace_job_indexes
Revises: migrate_marketplace_to_numeric
Create Date: 2026-07-06 00:00:04.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "add_marketplace_job_indexes"
down_revision = "migrate_marketplace_to_numeric"
branch_labels = None
depends_on = None


# (table, column, index_name) for each index.
_INDEXES: list[tuple[str, str, str]] = [
    ("marketplaceoffer", "status", "ix_marketplaceoffer_status"),
    ("marketplace_bid", "status", "ix_marketplace_bid_status"),
    ("job", "state", "ix_job_state"),
]


def upgrade() -> None:
    for table, column, index_name in _INDEXES:
        op.create_index(index_name, table, [column], if_not_exists=True)


def downgrade() -> None:
    for table, _column, index_name in _INDEXES:
        op.drop_index(index_name, table_name=table, if_exists=True)
