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


# The expression must match what the query emits or the planner ignores the index:
#   SQLite   -> JSON_EXTRACT("transaction".payload, \'$."job_id"\')
#   Postgres -> (transaction.payload ->> \'job_id\')
_EXPRESSIONS = {
    "sqlite": """json_extract(payload, \'$."job_id"\')""",
    "postgresql": """(payload ->> \'job_id\')""",
}


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    expression = _EXPRESSIONS.get(dialect)
    if expression is None:
        # Unknown dialect: the job_id filter still works, just unindexed.
        return
    op.execute(f'CREATE INDEX IF NOT EXISTS {INDEX_NAME} ON "transaction" ({expression})')


def downgrade() -> None:
    if op.get_bind().dialect.name not in _EXPRESSIONS:
        return
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
