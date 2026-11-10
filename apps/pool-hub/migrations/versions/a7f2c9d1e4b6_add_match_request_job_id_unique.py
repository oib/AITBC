"""Add UniqueConstraint(job_id) to match_requests (#1553).

Duplicate POST /v1/match calls used to append duplicate MatchRequest and
MatchResult rows; billing integration sums those rows into api_calls /
compute totals, so a retried match inflated billing. The model now declares
the constraint (fresh DBs get it from create_all); this revision adds it to
existing databases after collapsing duplicates — freshest request per
job_id wins, and its match_results are deleted with it (the FK cascade
covers Postgres; the explicit delete keeps sqlite dev DBs honest).

Revision ID: a7f2c9d1e4b6
Revises: f6a1b2c3d4e5
"""

from alembic import op
from sqlalchemy import inspect, text

revision = "a7f2c9d1e4b6"
down_revision = "f6a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "match_requests" not in inspect(bind).get_table_names():
        return
    # Dedup: keep the freshest request per job_id. Window functions work on
    # both PostgreSQL and the sqlite versions used in tests/development.
    op.execute(
        text(
            """
            DELETE FROM match_results
            WHERE request_id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY job_id
                               ORDER BY created_at DESC
                           ) AS rn
                    FROM match_requests
                ) ranked
                WHERE rn > 1
            )
            """
        )
    )
    op.execute(
        text(
            """
            DELETE FROM match_requests
            WHERE id NOT IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY job_id
                               ORDER BY created_at DESC
                           ) AS rn
                    FROM match_requests
                ) ranked
                WHERE rn = 1
            )
            """
        )
    )
    # SQLite cannot ALTER a constraint in place — batch mode rebuilds the
    # table (same pattern as d4c3e7f8a9b0). PostgreSQL keeps the native ALTER.
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("match_requests", recreate="always") as batch_op:
            batch_op.create_unique_constraint("uq_match_request_job_id", ["job_id"])
    else:
        op.create_unique_constraint("uq_match_request_job_id", "match_requests", ["job_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if "match_requests" not in inspect(bind).get_table_names():
        return
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("match_requests", recreate="always") as batch_op:
            batch_op.drop_constraint("uq_match_request_job_id", type_="unique")
    else:
        op.drop_constraint("uq_match_request_job_id", "match_requests", type_="unique")
