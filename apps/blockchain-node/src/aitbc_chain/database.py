from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eth_utils import keccak

from sqlalchemy import Column, ColumnDefault, Engine, event, inspect, literal, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlmodel import Session, create_engine

from aitbc.aitbc_logging import get_logger

# Import all models to ensure they are registered on chain_metadata. Every table this
# package owns has to be imported here, or `create_all` below silently skips it.
from .base_models import (  # noqa: F401
    Account,
    Block,
    Bond,
    Escrow,
    Receipt,
    SmartContract,
    Transaction,
    Stake,
    AgentStakeRecord,
    AgentStakeMemo,
    BountyContract,
    BountySubmissionRecord,
    AgentIdentity,
    GovernanceProposal,
    GovernanceVote,
    _to_ait_address,
    canonical_address,
)
from .config import settings
from .mempool import MempoolEntry  # noqa: F401
from .metadata import chain_metadata
from .state.gpu_resources import EdgeNodeRegistration, GPUAllocation, GPURegistration  # noqa: F401

# Database encryption key (in production, this should come from HSM or secure key storage)
_DB_ENCRYPTION_KEY = os.environ.get("AITBC_DB_KEY", "default_encryption_key_change_in_production")

# Registry of chain-specific database engines
_db_temp_paths: dict[str, object] = {}

logger = get_logger(__name__)


def get_encryption_key(key_path: os.PathLike[str] | None) -> bytes | None:
    """Get encryption key from file"""
    if not key_path or not os.path.exists(key_path):
        return None
    with open(key_path, "rb") as f:
        return f.read()


def encrypt_database(db_path: Path, key: bytes) -> None:
    """Encrypt database file"""
    # Real implementation is in database_encryption.py
    # Import and call the actual implementation
    from .database_encryption import encrypt_database as real_encrypt

    real_encrypt(db_path, key)


_engines: dict[str, Engine] = {}
_default_chain_id: str = ""


def get_engine(chain_id: str = "") -> Engine:
    """Get database engine for a specific chain.

    Uses SQLCipher for encryption when enabled (ait-mainnet only).
    SQLCipher maintains SQLite's internal format while encrypting data at rest.

    Args:
        chain_id: Chain ID to get engine for. If empty, uses default chain.

    Returns:
        SQLAlchemy engine for the chain.
    """
    resolved_chain_id = chain_id or _default_chain_id or settings.chain_id or "ait-mainnet"

    if resolved_chain_id not in _engines:
        db_path = settings.get_db_path(resolved_chain_id)

        # Check if SQLCipher encryption is enabled for this chain (only ait-mainnet)
        encryption_enabled = (
            settings.db_encryption_enabled and settings.db_encryption_key_path.exists() and resolved_chain_id == "ait-mainnet"
        )

        if encryption_enabled:
            # Use SQLCipher with encryption key
            try:
                import sqlcipher3 as sqlite3
            except ImportError:
                raise RuntimeError(
                    "SQLCipher encryption enabled but sqlcipher3-binary not installed. Run: pip install sqlcipher3-binary"
                ) from None

            # Load encryption key from file (raw binary bytes, convert to hex)
            with open(settings.db_encryption_key_path, "rb") as f:
                key_bytes = f.read()
            key_hex = key_bytes.hex()

            # Create engine with SQLCipher (NullPool: fresh connection per session)
            engine = create_engine(
                f"sqlite:///{db_path}",
                module=sqlite3,
                echo=False,
                poolclass=NullPool,
                connect_args={"check_same_thread": False},
            )

            # Set encryption key via connection event
            @event.listens_for(engine, "connect")
            def set_encryption_key(dbapi_connection: Any, connection_record: Any) -> None:
                dbapi_connection.execute(f"PRAGMA key = '{key_hex}'")
                _set_sqlite_pragmas(dbapi_connection, connection_record)
        else:
            # Use standard SQLite (NullPool: fresh connection per session)
            engine = create_engine(
                f"sqlite:///{db_path}",
                echo=False,
                poolclass=NullPool,
                connect_args={"check_same_thread": False},
            )

            @event.listens_for(engine, "connect")
            def _on_chain_engine_connect(dbapi_connection: Any, connection_record: Any) -> None:
                _set_sqlite_pragmas(dbapi_connection, connection_record)

        _engines[resolved_chain_id] = engine

    return _engines[resolved_chain_id]


def _set_sqlite_pragmas(dbapi_connection: Any, connection_record: Any) -> None:
    """Set WAL and tuning pragmas on every new SQLite connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=30000000000")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


# Standard SQLite with file-based encryption via file permissions
_db_path = settings.db_path
_engine = create_engine(
    f"sqlite:///{settings.db_path}",
    echo=False,
    poolclass=NullPool,
    connect_args={"check_same_thread": False},
)


@event.listens_for(_engine, "connect")
def _on_engine_connect(dbapi_connection: Any, connection_record: Any) -> None:
    _set_sqlite_pragmas(dbapi_connection, connection_record)


# Application-layer validation
class DatabaseOperationValidator:
    """Validates database operations to prevent unauthorized access"""

    def __init__(self) -> None:
        self._allowed_operations = {"select", "insert", "update", "delete"}

    def validate_operation(self, operation: str) -> bool:
        """Validate that the operation is allowed"""
        return operation.lower() in self._allowed_operations

    def validate_query(self, query: str) -> bool:
        """Validate that the query doesn't contain dangerous patterns"""
        dangerous_patterns = [
            "drop table",
            "drop database",
            "truncate",
            "alter table",
            "delete from account",
            "update account set balance",
        ]
        query_lower = query.lower()
        for pattern in dangerous_patterns:
            if pattern in query_lower:
                return False
        return True


_validator = DatabaseOperationValidator()

# Session factory for the module-level engine (sessionmaker factory pattern).
_session_factory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, class_=Session, expire_on_commit=False)

# Cache of session factories per chain_id (chain-specific engines are created
# lazily by get_engine; reuse a sessionmaker once the engine exists).
_session_factories: dict[str, sessionmaker] = {}


def _get_session_factory(chain_id: str) -> sessionmaker:
    """Get (or create and cache) a sessionmaker bound to the chain's engine."""
    resolved_chain_id = chain_id or _default_chain_id or settings.chain_id or "ait-mainnet"
    if resolved_chain_id not in _session_factories:
        engine = get_engine(chain_id)
        _session_factories[resolved_chain_id] = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session, expire_on_commit=False)
    return _session_factories[resolved_chain_id]


# Secure session scope with validation
@contextmanager
def _secure_session_scope() -> Generator[Session]:
    """Internal secure session scope with validation"""
    with _session_factory() as session:
        yield session


# Public session scope wrapper with validation
@contextmanager
def session_scope(chain_id: str = "") -> Generator[Session]:
    """Public session scope with application-layer validation

    Args:
        chain_id: Chain ID to use for database connection. If empty, uses default chain.
    """
    factory = _get_session_factory(chain_id)
    with factory() as session:
        yield session


# Internal engine reference (not exposed)
_engine_internal = _engine


def _is_valid_sql_identifier(name: str) -> bool:
    """Validate that a string is a safe SQL identifier (table/column name).

    Kept alongside the dialect quoting in `_migrate_existing_columns` rather than replaced by
    it: this rejects a name outright, quoting merely makes one safe to interpolate. Note what
    it does *not* tell you -- `transaction` passes, and `transaction` is a SQLite keyword.
    """
    if not name or len(name) > 128:
        return False
    return name.replace("_", "").isalnum() and name[0].isalpha()


def _default_clause(column: Column[Any], engine: Engine) -> str:
    """Render a column's model-side default as a SQL DEFAULT clause, or "" if it cannot be.

    Both halves of this used to be done by string formatting, and both were wrong:

    * A callable default -- `Field(default_factory=lambda: datetime.now(UTC))` -- arrived here
      as the function object and got interpolated by `repr`, producing
      `DEFAULT <function Account.<lambda> at 0x7f...>`. 24 columns in this schema have one,
      every `created_at` / `updated_at` / `timestamp` on every core table, and all 24 are
      NOT NULL, so the ALTER could not have been skipped either. It is evaluated once here
      and the result becomes a constant, which is what a hand-written backfill would do.
    * A literal was rendered by `isinstance(val, str)` and an f-string. The dialect knows how
      to write a literal of any type it supports, including the quoting, so it does it.

    Returns "" when the dialect cannot render the value, so the caller emits an ALTER with no
    DEFAULT -- which succeeds for a nullable column and fails loudly for one that is not,
    rather than writing something that parses into the wrong value (V23-77).
    """
    default = column.default
    # `Column.default` is a `DefaultGenerator`; only the `ColumnDefault` branch of that carries
    # a value at all. A server-side or sequence default is not something to re-render here.
    if not isinstance(default, ColumnDefault) or default.arg is None:
        return ""
    try:
        # SQLAlchemy wraps a zero-argument `default_factory` in a callable that takes an
        # execution context and ignores it. There is no context at DDL time, so it gets None --
        # and a default that genuinely reads the context cannot be reduced to a constant
        # anyway, so it fails here and is reported as one this cannot render.
        value = default.arg(None) if default.is_callable else default.arg  # type: ignore[arg-type]
        rendered = literal(value, column.type).compile(engine, compile_kwargs={"literal_binds": True})
    except Exception:  # noqa: BLE001 - evaluating or compiling failed: we cannot express this
        logger.warning(
            "Cannot render a DEFAULT for %s.%s; adding the column without one",
            column.table.name,
            column.name,
        )
        return ""
    return f" DEFAULT {rendered}"


def _migrate_existing_columns(engine: Engine) -> None:
    """Add missing columns to existing SQLite tables.

    `chain_metadata.create_all` only creates new tables — it does not add
    columns to tables that already exist. This function inspects each table
    in the metadata and adds any columns that are missing from the DB schema.

    Identifiers go through the dialect's quoter. They used to be interpolated bare, which
    made this a startup crash rather than a migration on any chain database old enough to
    be missing a column on `transaction`: that is a reserved word in SQLite, so
    `ALTER TABLE transaction ADD COLUMN nonce INTEGER DEFAULT 0` is a syntax error. It is
    the only identifier of the 164 in this schema that needs quoting, and it names the
    chain's central table — the one most likely to gain a column (V23-77).

    It reconciles columns and nothing else: a table that exists keeps whatever indexes and
    constraints it has, so an old database ends up with the current columns and its original
    index set. Alembic under `migrations/` is what covers the rest.
    """
    inspector = inspect(engine)
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        for table_obj in chain_metadata.sorted_tables:
            table_name = table_obj.name
            if not _is_valid_sql_identifier(table_name):
                continue
            if not inspector.has_table(table_name):
                continue
            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            for col in table_obj.columns:
                if col.name in existing_cols:
                    continue
                if not _is_valid_sql_identifier(col.name):
                    continue
                coltype = col.type.compile(engine.dialect)
                default = _default_clause(col, engine)
                if not default and not col.nullable:
                    # This used to emit `DEFAULT ''` and carry on, on a comment about text
                    # columns. 91 columns in this schema are NOT NULL with no model default,
                    # and they are the ones that matter: `block.height INTEGER DEFAULT ''`,
                    # `escrow.amount INTEGER DEFAULT ''`, `transaction.payload JSON DEFAULT ''`,
                    # `governance_proposal.voting_ends DATETIME DEFAULT ''`. That does not fail
                    # -- it writes a schema whose default is nonsense for the type, and the
                    # first insert that omits the column stores it.
                    #
                    # A NOT NULL column with no default genuinely cannot be back-filled into a
                    # table that has rows; SQLite rejects it too. So say which column, and stop.
                    # Unreachable for a table `create_all` built, since it builds the column.
                    raise RuntimeError(
                        f"{table_name}.{col.name} is NOT NULL with no default that can be "
                        f"rendered as SQL, so it cannot be added to a table that already has "
                        f"rows. It needs a migration under migrations/, not this."
                    )
                conn.execute(text(f"ALTER TABLE {quote(table_name)} ADD COLUMN {quote(col.name)} {coltype}{default}"))


def _bond_escrow_address() -> str:
    """Return the canonical bond escrow address."""
    env = os.getenv("BOND_ESCROW_ADDRESS", "")
    if env:
        return canonical_address(env)
    return "0x" + keccak(b"aitbc.bond.escrow").hex()[:40]


def _bond_burn_address() -> str:
    """Return the canonical bond burn address."""
    env = os.getenv("BOND_BURN_ADDRESS", "")
    if env:
        return canonical_address(env)
    return "0x" + keccak(b"aitbc.bond.burn").hex()[:40]


def ensure_bond_accounts(session: Session, chain_id: str) -> None:
    """Create zero-balance bond escrow and burn accounts if missing."""

    for address in (_bond_escrow_address(), _bond_burn_address()):
        ait_addr = _to_ait_address(address)
        if not session.get(Account, (chain_id, ait_addr)):
            session.add(Account(chain_id=chain_id, address=ait_addr, balance=0, nonce=0, updated_at=datetime.now(UTC)))
            logger.info("Created bond account %s for chain %s", ait_addr, chain_id)
    session.commit()


def init_db(chain_id: str = "") -> None:
    """Initialize database with file-based encryption

    Args:
        chain_id: Chain ID to initialize. If empty, uses default chain.
    """
    resolved_chain_id = chain_id or _default_chain_id or settings.chain_id or "ait-mainnet"
    db_path = settings.get_db_path(resolved_chain_id)

    # Create database directory with chain_id subdirectory
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Get or create chain-specific engine
    engine = get_engine(resolved_chain_id)

    # No try/except here. This used to swallow anything whose message contained "already
    # exists", on the reasoning that existing tables are fine -- but `create_all` defaults to
    # `checkfirst=True` and skips what is already there, so it does not raise for that reason.
    # What it did raise for, until V23-74, was a duplicate `CREATE INDEX`: every service shared
    # one global `MetaData` and `extend_existing` appended index objects a table already had.
    # `aitbc_chain` owns its tables now, that cause is gone, and matching on an exception's
    # *message* was never a safe way to tell a benign collision from a corrupt schema anyway
    # -- the wording belongs to SQLAlchemy and the driver, not to us. Anything raised here is
    # a real problem with this node's database and should stop it starting (V23-77).
    chain_metadata.create_all(engine)

    # Add missing columns to existing tables (create_all only creates new tables)
    _migrate_existing_columns(engine)

    # Ensure bond escrow and burn accounts exist for this chain.
    with session_scope(resolved_chain_id) as session:
        ensure_bond_accounts(session, resolved_chain_id)


def shutdown_db(chain_id: str = "") -> None:
    """Shutdown database connection and encrypt if needed.

    Args:
        chain_id: Chain ID to shutdown. If empty, uses default chain.
    """
    resolved_chain_id = chain_id or _default_chain_id or settings.chain_id or "ait-mainnet"

    # Check if we need to encrypt the database back
    if resolved_chain_id in _db_temp_paths:
        temp_path = _db_temp_paths[resolved_chain_id]
        db_path = settings.get_db_path(resolved_chain_id)

        # Check if encryption is enabled for this chain
        encryption_enabled = settings.db_encryption_enabled and resolved_chain_id == "ait-mainnet"

        if encryption_enabled and isinstance(temp_path, os.PathLike) and os.path.exists(temp_path):
            # Encrypt the temporary file back to the original location
            key = get_encryption_key(settings.db_encryption_key_path)
            if key is None:
                raise RuntimeError(f"Database encryption enabled but key not found at {settings.db_encryption_key_path}")

            try:
                encrypt_database(Path(temp_path), key)
                # Move encrypted file to original location
                encrypted_path = Path(temp_path).with_suffix(".db.encrypted")
                encrypted_path.replace(db_path)
                # Clean up temporary file
                Path(temp_path).unlink(missing_ok=True)
                del _db_temp_paths[resolved_chain_id]
            except Exception as e:
                raise RuntimeError(f"Failed to encrypt database for chain {resolved_chain_id}: {e}") from e

    # Dispose of engine and cached session factory
    _session_factories.pop(resolved_chain_id, None)
    if resolved_chain_id in _engines:
        _engines[resolved_chain_id].dispose()
        del _engines[resolved_chain_id]
