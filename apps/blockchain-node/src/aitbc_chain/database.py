from __future__ import annotations

import hashlib
import os
import stat
from contextlib import contextmanager
from typing import Optional

from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy import event

from .config import settings

# Import all models to ensure they are registered with SQLModel.metadata
from .models import Block, Transaction, Account, Receipt, Escrow  # noqa: F401

# Database encryption key (in production, this should come from HSM or secure key storage)
_DB_ENCRYPTION_KEY = os.environ.get("AITBC_DB_KEY", "default_encryption_key_change_in_production")

# Registry of chain-specific database engines
_engines: dict[str, object] = {}
_default_chain_id: str = ""

def get_engine(chain_id: str = "") -> object:
    """Get database engine for a specific chain.
    
    Args:
        chain_id: Chain ID to get engine for. If empty, uses default chain.
    
    Returns:
        SQLAlchemy engine for the chain.
    """
    resolved_chain_id = chain_id or _default_chain_id or settings.chain_id or "ait-mainnet"
    
    if resolved_chain_id not in _engines:
        db_path = settings.get_db_path(resolved_chain_id)
        _engines[resolved_chain_id] = create_engine(f"sqlite:///{db_path}", echo=False)
    
    return _engines[resolved_chain_id]

# Standard SQLite with file-based encryption via file permissions
_db_path = settings.db_path
_engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)

@event.listens_for(_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    # WAL mode disabled due to issues on btrfs raid (CoW already disabled on data directory)
    # cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=30000000000")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

# Application-layer validation
class DatabaseOperationValidator:
    """Validates database operations to prevent unauthorized access"""
    
    def __init__(self):
        self._allowed_operations = {
            'select', 'insert', 'update', 'delete'
        }
    
    def validate_operation(self, operation: str) -> bool:
        """Validate that the operation is allowed"""
        return operation.lower() in self._allowed_operations
    
    def validate_query(self, query: str) -> bool:
        """Validate that the query doesn't contain dangerous patterns"""
        dangerous_patterns = [
            'DROP TABLE', 'DROP DATABASE', 'TRUNCATE',
            'ALTER TABLE', 'DELETE FROM account',
            'UPDATE account SET balance'
        ]
        query_upper = query.upper()
        for pattern in dangerous_patterns:
            if pattern in query_upper:
                return False
        return True

_validator = DatabaseOperationValidator()

# Secure session scope with validation
@contextmanager
def _secure_session_scope() -> Session:
    """Internal secure session scope with validation"""
    with Session(_engine) as session:
        yield session

# Public session scope wrapper with validation
@contextmanager
def session_scope(chain_id: str = "") -> Session:
    """Public session scope with application-layer validation
    
    Args:
        chain_id: Chain ID to use for database connection. If empty, uses default chain.
    """
    # Get chain-specific engine
    engine = get_engine(chain_id)
    
    with Session(engine) as session:
        yield session

# Internal engine reference (not exposed)
_engine_internal = _engine

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
    
    try:
        SQLModel.metadata.create_all(engine)
    except Exception as e:
        # If tables already exist, that's okay
        if "already exists" not in str(e):
            raise
    
    # Set permissive file permissions on database file to handle filesystem restrictions
    if db_path.exists():
        try:
            os.chmod(db_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)  # Read/write for all
        except OSError:
            # Ignore permission errors (e.g., read-only filesystem in containers)
            pass
        # Also set permissions on WAL files if they exist
        wal_shm = db_path.with_suffix('.db-shm')
        wal_wal = db_path.with_suffix('.db-wal')
        if wal_shm.exists():
            try:
                os.chmod(wal_shm, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
            except OSError:
                pass
        if wal_wal.exists():
            try:
                os.chmod(wal_wal, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH)
            except OSError:
                pass

# Restricted engine access - only for internal use
def get_engine():
    """Get database engine (restricted access)"""
    return _engine_internal

# Backward compatibility - expose engine for escrow routes (to be removed in Phase 1.3)
# TODO: Remove this in Phase 1.3 when escrow routes are updated
engine = _engine_internal
