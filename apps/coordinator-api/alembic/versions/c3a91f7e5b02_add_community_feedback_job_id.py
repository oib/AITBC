"""Add job_id to community_feedback with one-review-per-(reviewer, job) uniqueness.

Revision ID: c3a91f7e5b02
Revises: add_partner_integration_tables
Create Date: 2026-09-27 00:00:00.000000

Anchors community feedback to a completed job: a caller must name a job they
paid this agent for, and the unique index on (reviewer_id, job_id) stops a
single completed job underwriting unlimited ratings. job_id stays nullable so
existing rows and admin-posted feedback keep working; NULLs never collide in
the unique index.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c3a91f7e5b02"
down_revision: str | None = "add_partner_integration_tables"
branch_labels: str | None = None
depends_on: str | None = None

INDEX_NAME = "uq_community_feedback_reviewer_job"


def _column_exists(table: str, column: str) -> bool:
    """Guard against duplicate-column failures on fresh databases where the
    model's ``create_all`` already produced the current schema."""
    if context.is_offline_mode():
        return False
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def _index_or_constraint_exists(table: str, name: str) -> bool:
    """True when a unique index or unique constraint of this name exists.

    On Postgres a model-level UniqueConstraint creates a backing index with the
    constraint's own name, which ``get_indexes`` lists; on SQLite the same
    constraint surfaces only as ``sqlite_autoindex_…``, so the explicit index
    is still created there (harmless — enforcement is identical).
    """
    if context.is_offline_mode():
        return False
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    names = {i["name"] for i in inspect(bind).get_indexes(table)}
    names |= {c["name"] for c in inspect(bind).get_unique_constraints(table) if c.get("name")}
    return name in names


def upgrade() -> None:
    if not _column_exists("community_feedback", "job_id"):
        op.add_column("community_feedback", sa.Column("job_id", sa.String(length=64), nullable=True))
    if not _index_or_constraint_exists("community_feedback", INDEX_NAME):
        op.create_index(INDEX_NAME, "community_feedback", ["reviewer_id", "job_id"], unique=True)


def downgrade() -> None:
    if _index_or_constraint_exists("community_feedback", INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="community_feedback")
    if _column_exists("community_feedback", "job_id"):
        op.drop_column("community_feedback", "job_id")
