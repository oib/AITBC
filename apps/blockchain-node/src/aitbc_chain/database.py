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
            settings.db_encryption_enabled and 
            settings.db_encryption_key_path.exists() and 
            resolved_chain_id == "ait-mainnet"
        )
        
        if encryption_enabled:
            # Use SQLCipher with encryption key
            try:
                import sqlcipher3 as sqlite3
            except ImportError:
                raise RuntimeError(
                    "SQLCipher encryption enabled but sqlcipher3-binary not installed. "
                    "Run: pip install sqlcipher3-binary"
                )
            
            # Load encryption key from file (raw binary bytes, convert to hex)
            with open(settings.db_encryption_key_path, 'rb') as f:
                key_bytes = f.read()
            key_hex = key_bytes.hex()
            
            # Create engine with SQLCipher
            engine = create_engine(
                f"sqlite:///{db_path}",
                module=sqlite3,
                echo=False
            )
            
            # Set encryption key via connection event
            @event.listens_for(engine, "connect")
            def set_encryption_key(dbapi_connection, connection_record):
                dbapi_connection.execute(f"PRAGMA key = '{key_hex}'")
                dbapi_connection.execute("PRAGMA journal_mode=WAL")
                dbapi_connection.execute("PRAGMA synchronous=NORMAL")
        else:
            # Use standard SQLite
            engine = create_engine(f"sqlite:///{db_path}", echo=False)
            
            @event.listens_for(engine, "connect")
            def set_wal_mode(dbapi_connection, connection_record):
                dbapi_connection.execute("PRAGMA journal_mode=WAL")
                dbapi_connection.execute("PRAGMA synchronous=NORMAL")
        
        _engines[resolved_chain_id] = engine
    
    return _engines[resolved_chain_id]

# Standard SQLite with file-based encryption via file permissions
_db_path = settings.db_path
_engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)

@event.listens_for(_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
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
        encryption_enabled = (
            settings.db_encryption_enabled and 
            resolved_chain_id == "ait-mainnet"
        )
        
        if encryption_enabled and temp_path.exists():
            # Encrypt the temporary file back to the original location
            key = get_encryption_key(settings.db_encryption_key_path)
            if key is None:
                raise RuntimeError(f"Database encryption enabled but key not found at {settings.db_encryption_key_path}")
            
            try:
                encrypt_database(temp_path, key)
                # Move encrypted file to original location
                encrypted_path = temp_path.with_suffix('.db.encrypted')
                encrypted_path.replace(db_path)
                # Clean up temporary file
                temp_path.unlink(missing_ok=True)
                del _db_temp_paths[resolved_chain_id]
            except Exception as e:
                raise RuntimeError(f"Failed to encrypt database for chain {resolved_chain_id}: {e}")
    
    # Dispose of engine
    if resolved_chain_id in _engines:
        _engines[resolved_chain_id].dispose()
        del _engines[resolved_chain_id]
