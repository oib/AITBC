"""Index transaction payload job_id for settlement lookups.

Settlement asks the chain "has this job already been released?" before paying a
provider. Without an index that question scans every transaction row, and the
answer gates a real payout, so it has to stay cheap as the chain grows.

Revision ID: b7f3c1a90d24
Revises: d4e8b91c0a37
"""

from alembic import op

revision: str = "b7f3c1a90d24"
down_revision: str | None = "d4e8b91c0a37"
branch_labels: str | None = None
depends_on: str | None = None

INDEX_NAME = "ix_transaction_payload_job_id"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # The expression index is Postgres-specific; SQLite deployments fall back to
        # the JSON extraction filter without an index.
        return
    op.execute(f'CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON "transaction" ((payload ->> \'job_id\'))')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
