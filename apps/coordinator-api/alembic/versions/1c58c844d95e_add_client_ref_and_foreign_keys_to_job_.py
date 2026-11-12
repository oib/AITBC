"""add client_ref and foreign keys to job, agent_executions, gpu_bookings

Revision ID: 1c58c844d95e
Revises: 5d8339a13a12
Create Date: 2026-09-01 18:06:07.108621+00:00

"""

from collections.abc import Sequence

from alembic import op, context
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1c58c844d95e"
down_revision: str | Sequence[str] | None = "5d8339a13a12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(bind: sa.engine.Connection, table_name: str) -> bool:
    """Check whether a table exists in the current database.

    In offline SQL generation mode the database is assumed to be in the
    historical state described by prior revisions, so the table is assumed
    to exist.
    """
    if context.is_offline_mode():
        return True
    return table_name in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table_name: str, column: str) -> bool:
    """Check whether a column already exists on a table.

    When ``001_initial_migration`` runs ``SQLModel.metadata.create_all`` on a
    fresh database, the current models (which already include ``client_ref``)
    are created. Later migrations that ``ALTER TABLE ... ADD COLUMN`` then fail
    with ``duplicate column name``. This guard skips the ALTER when the column
    is already present, which is the pattern established by
    ``c7d1f4a9e230`` and ``236edfbd9728`` in this repo.
    """
    if context.is_offline_mode():
        return False
    if not _table_exists(bind, table_name):
        return False
    return any(c["name"] == column for c in sa.inspect(bind).get_columns(table_name))


def _index_exists(bind: sa.engine.Connection, table_name: str, index_name: str) -> bool:
    """Check whether an index already exists on a table."""
    if context.is_offline_mode():
        return False
    if not _table_exists(bind, table_name):
        return False
    return any(idx["name"] == index_name for idx in sa.inspect(bind).get_indexes(table_name))


def _add_client_ref_columns(bind: sa.engine.Connection) -> None:
    """Step 1: add client_ref columns to preserve the original caller string.

    Guard against duplicate-column failures on fresh databases where
    001_initial_migration has already created the current schema via
    SQLModel.metadata.create_all (which includes client_ref).
    """
    for table in ("job", "agent_executions", "gpu_bookings"):
        if not _column_exists(bind, table, "client_ref"):
            op.add_column(
                table,
                sa.Column("client_ref", sa.String(length=255), nullable=True),
            )


def _collect_unresolved_refs(session, tables: tuple[str, ...]) -> dict[str, str]:
    """Step 2: backfill client_ref and collect distinct client_id values
    that are not yet valid users."""
    from sqlalchemy import select, text

    from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

    unresolved_refs: dict[str, str] = {}
    for table in tables:
        session.execute(text(f"UPDATE {table} SET client_ref = client_id"))  # nosec
        client_ids = set()
        for row in session.execute(text(f"SELECT DISTINCT client_id FROM {table}")).all():  # nosec B608
            if row[0]:
                client_ids.add(row[0])
        for raw_client_id in client_ids:
            if raw_client_id in unresolved_refs:
                continue
            user = session.get(User, raw_client_id)
            if user:
                continue
            wallet = session.exec(select(Wallet).where(Wallet.address == raw_client_id.lower())).scalars().first()
            if wallet:
                user = session.get(User, wallet.user_id)
                if user:
                    continue
            unresolved_refs[raw_client_id] = ""
    return unresolved_refs


def _unique_placeholder_username(existing_usernames: set[str], base: str) -> str:
    """Return a username not already present in ``existing_usernames``,
    registering the chosen candidate in the set."""
    import uuid as _uuid

    candidate = base[:255]
    if candidate not in existing_usernames:
        existing_usernames.add(candidate)
        return candidate
    suffix = _uuid.uuid4().hex[:8]
    candidate = f"{base[:246]}_{suffix}"
    while candidate in existing_usernames:
        suffix = _uuid.uuid4().hex[:8]
        candidate = f"{base[:246]}_{suffix}"
    existing_usernames.add(candidate)
    return candidate


def _create_placeholder_users(session, unresolved_refs: dict[str, str]) -> None:
    """Create placeholder users (and wallets for 0x addresses) for every
    unresolved client_id, recording the new users.id back into
    ``unresolved_refs``."""
    import uuid as _uuid
    from datetime import UTC, datetime
    from decimal import Decimal

    from sqlalchemy import text

    from coordinator_api.contexts.infrastructure.domain.user import User, Wallet

    now = datetime.now(UTC)
    existing_usernames = {u[0] for u in session.execute(text("SELECT username FROM users")).all()}

    for raw_client_id in unresolved_refs:
        user_id = str(_uuid.uuid4())
        is_wallet = raw_client_id.startswith("0x") and len(raw_client_id) == 42
        if is_wallet:
            address = raw_client_id.lower()
            username = _unique_placeholder_username(existing_usernames, f"user_{address[-8:]}_{_uuid.uuid4().hex[:8]}")
            email = f"wallet_{address[-8:]}_{_uuid.uuid4().hex[:8]}@aitbc.local"
        else:
            username = _unique_placeholder_username(existing_usernames, raw_client_id[:255])
            email = f"placeholder_{_uuid.uuid4().hex[:8]}@aitbc.local"

        user = User(
            id=user_id,
            email=email,
            username=username,
            status="active",
            created_at=now,
            updated_at=now,
            last_login=now,
        )
        session.add(user)
        if is_wallet:
            wallet = Wallet(
                user_id=user_id,
                address=address,
                balance=Decimal("0.0"),
                created_at=now,
                updated_at=now,
            )
            session.add(wallet)
        session.flush()
        unresolved_refs[raw_client_id] = user_id

    session.commit()


def _repoint_client_ids(session, tables: tuple[str, ...], unresolved_refs: dict[str, str]) -> None:
    """Step 3: repoint client_id in each table to the canonical users.id."""
    from sqlalchemy import text

    for table in tables:
        for raw_client_id, user_id in unresolved_refs.items():
            session.execute(
                text(f"UPDATE {table} SET client_id = :user_id WHERE client_id = :raw"),  # nosec
                {"user_id": user_id, "raw": raw_client_id},
            )
    session.commit()


def _backfill_client_refs(bind: sa.engine.Connection, tables: tuple[str, ...]) -> None:
    """Steps 2-3: backfill client_ref, create placeholder users for
    unresolvable client_id values, and repoint client_id to users.id."""
    from sqlmodel import Session

    session = Session(bind)
    unresolved_refs = _collect_unresolved_refs(session, tables)
    if unresolved_refs:
        _create_placeholder_users(session, unresolved_refs)
        _repoint_client_ids(session, tables, unresolved_refs)


def _add_client_fk_constraints(bind: sa.engine.Connection, tables: tuple[str, ...]) -> None:
    """Step 4: add foreign keys.

    SQLite requires table recreation for ADD FOREIGN KEY, so use
    batch_alter_table. Offline SQL generation cannot reflect the live table
    and is not required to enforce referential integrity, so we skip FK
    creation in that mode.
    """
    if context.is_offline_mode():
        return
    for table in tables:
        if bind.dialect.name == "sqlite":
            with op.batch_alter_table(table, recreate="always") as batch_op:
                batch_op.create_foreign_key(
                    op.f(f"fk_{table}_client_id_users"),
                    "users",
                    ["client_id"],
                    ["id"],
                )
        else:
            op.create_foreign_key(
                op.f(f"fk_{table}_client_id_users"),
                table,
                "users",
                ["client_id"],
                ["id"],
            )


def _add_client_ref_indexes(bind: sa.engine.Connection, tables: tuple[str, ...]) -> None:
    """Step 5: add indexes for client_ref (SQLModel index=True)."""
    for table in tables:
        index_name = op.f(f"ix_{table}_client_ref")
        if not _index_exists(bind, table, index_name):
            op.create_index(
                index_name,
                table,
                ["client_ref"],
                unique=False,
            )


def upgrade() -> None:
    """Add client_ref columns, backfill references, and enforce client_id FKs.

    The existing ``client_id`` column is overloaded: it may be a JWT user id
    (UUID), a wallet address, or an opaque test/operator label. This migration
    preserves the original caller string in a new ``client_ref`` column and
    makes ``client_id`` a canonical foreign key to ``users.id``. Any
    unresolvable ``client_id`` values become placeholder users so existing rows
    do not violate the new foreign key.
    """
    bind = op.get_bind()
    tables = ("job", "agent_executions", "gpu_bookings")

    _add_client_ref_columns(bind)

    # Offline SQL generation (--sql) targets a fresh, empty database; there is no
    # data to backfill. Skip the data migration so the generated SQL only
    # contains schema changes.
    if not context.is_offline_mode():
        _backfill_client_refs(bind, tables)

    _add_client_fk_constraints(bind, tables)
    _add_client_ref_indexes(bind, tables)


def downgrade() -> None:
    """Downgrade schema."""
    for table in ("job", "agent_executions", "gpu_bookings"):
        op.drop_index(op.f(f"ix_{table}_client_ref"), table_name=table, if_exists=True)
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table(table, recreate="always") as batch_op:
                batch_op.drop_constraint(op.f(f"fk_{table}_client_id_users"), type_="foreignkey")
        else:
            op.drop_constraint(op.f(f"fk_{table}_client_id_users"), table_name=table, type_="foreignkey")
        op.drop_column(table, "client_ref")
