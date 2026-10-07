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
    constraint is reported by ``get_unique_constraints`` under its declared
    name while physically living as a ``sqlite_autoindex_…``. Either way the
    explicit index is skipped when the constraint already exists.
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
    # The baseline's plain job_id index is destroyed by the SQLite batch
    # downgrade along with the column; restore it so a downgrade/upgrade
    # round-trip is lossless.
    if _column_exists("community_feedback", "job_id") and not _physical_index_exists(
        "community_feedback", "ix_community_feedback_job_id"
    ):
        op.create_index("ix_community_feedback_job_id", "community_feedback", ["job_id"], unique=False)


def _unique_constraint_exists(table: str, name: str) -> bool:
    """True when a *named* unique constraint carries this name.

    Distinct from ``_index_or_constraint_exists``: on SQLite a declared
    ``UniqueConstraint`` surfaces through ``get_unique_constraints`` by name
    while physically living only as a ``sqlite_autoindex_…`` — which
    ``DROP INDEX`` cannot remove. Downgrade must not conflate the two.
    """
    if context.is_offline_mode():
        return False
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return name in {c["name"] for c in inspect(bind).get_unique_constraints(table) if c.get("name")}


def _physical_index_exists(table: str, name: str) -> bool:
    """True when a real (droppable) index of this name exists."""
    if context.is_offline_mode():
        return False
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return name in {i["name"] for i in inspect(bind).get_indexes(table)}


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # SQLite cannot DROP COLUMN a column that a constraint or index
        # references; a batch rebuild recreates the table without job_id and
        # drops both the physical index (live databases) and the named
        # constraint (fresh frozen-001 builds) with it.
        with op.batch_alter_table("community_feedback") as batch_op:
            # Every dependent of job_id must go before the column: the plain
            # index and, depending on how the schema was built, either a
            # standalone unique index (upgraded live databases) or a named
            # unique constraint (fresh frozen-001 builds).
            if _physical_index_exists("community_feedback", "ix_community_feedback_job_id"):
                batch_op.drop_index("ix_community_feedback_job_id")
            if _physical_index_exists("community_feedback", INDEX_NAME):
                batch_op.drop_index(INDEX_NAME)
            if _unique_constraint_exists("community_feedback", INDEX_NAME):
                batch_op.drop_constraint(INDEX_NAME, type_="unique")
            if _column_exists("community_feedback", "job_id"):
                batch_op.drop_column("job_id")
        return
    if _unique_constraint_exists("community_feedback", INDEX_NAME):
        op.drop_constraint(INDEX_NAME, "community_feedback", type_="unique")
    elif _physical_index_exists("community_feedback", INDEX_NAME):
        op.drop_index(INDEX_NAME, table_name="community_feedback")
    if _column_exists("community_feedback", "job_id"):
        op.drop_column("community_feedback", "job_id")
