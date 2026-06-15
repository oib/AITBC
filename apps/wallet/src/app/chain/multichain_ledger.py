"""
Multi-Chain Ledger Adapter for Wallet Daemon

Chain-specific storage and ledger management for wallet operations
across multiple blockchain networks.
"""
import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from aitbc import get_logger

from .manager import ChainManager

logger = get_logger(__name__)
CHAIN_ID_PATTERN = re.compile('^[a-zA-Z0-9_-]+$')

def _validate_chain_id(chain_id: str) -> None:
    """Validate chain_id to prevent SQL injection via table name interpolation."""
    if not isinstance(chain_id, str):
        raise TypeError('chain_id must be a string')
    if not CHAIN_ID_PATTERN.match(chain_id):
        raise ValueError(f'Invalid chain_id format: {chain_id!r}')

@dataclass
class ChainLedgerRecord:
    """Chain-specific ledger record"""
    chain_id: str
    wallet_id: str
    event_type: str
    timestamp: datetime
    data: dict[str, Any]
    success: bool = True

@dataclass
class ChainWalletMetadata:
    """Chain-specific wallet metadata"""
    chain_id: str
    wallet_id: str
    public_key: str
    address: str | None
    metadata: dict[str, str]
    created_at: datetime
    updated_at: datetime

class MultiChainLedgerAdapter:
    """Multi-chain ledger adapter with chain-specific storage"""

    def __init__(self, chain_manager: ChainManager, base_data_path: Path | None=None):
        self.chain_manager = chain_manager
        self.base_data_path = base_data_path or Path('./data')
        self.base_data_path.mkdir(parents=True, exist_ok=True)
        self.chain_connections: dict[str, sqlite3.Connection] = {}
        self.chain_locks: dict[str, threading.Lock] = {}
        self._initialize_chain_databases()

    def _initialize_chain_databases(self) -> None:
        """Initialize database for each chain"""
        for chain in self.chain_manager.list_chains():
            self._init_chain_database(chain.chain_id)

    def _get_chain_db_path(self, chain_id: str) -> Path:
        """Get database path for a specific chain"""
        _validate_chain_id(chain_id)
        chain = self.chain_manager.get_chain(chain_id)
        if chain and chain.ledger_db_path:
            return Path(chain.ledger_db_path)
        return self.base_data_path / f'wallet_ledger_{chain_id}.db'

    def _init_chain_database(self, chain_id: str) -> None:
        """Initialize database for a specific chain"""
        _validate_chain_id(chain_id)
        try:
            db_path = self._get_chain_db_path(chain_id)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path)
            self.chain_connections[chain_id] = conn
            self.chain_locks[chain_id] = threading.Lock()
            with self.chain_locks[chain_id]:
                self._create_chain_schema(conn, chain_id)
            logger.info('Initialized database for chain: %s', chain_id)
        except Exception as e:
            logger.error('Failed to initialize database for chain %s: %s', chain_id, e)

    def _create_chain_schema(self, conn: sqlite3.Connection, chain_id: str) -> None:
        """Create database schema for a specific chain"""
        cursor = conn.cursor()
        cursor.execute(f'\n            CREATE TABLE IF NOT EXISTS wallet_metadata_{chain_id} (\n                wallet_id TEXT PRIMARY KEY,\n                public_key TEXT NOT NULL,\n                address TEXT,\n                metadata TEXT,\n                created_at TEXT NOT NULL,\n                updated_at TEXT NOT NULL\n            )\n        ')
        cursor.execute(f'\n            CREATE TABLE IF NOT EXISTS ledger_events_{chain_id} (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                wallet_id TEXT NOT NULL,\n                event_type TEXT NOT NULL,\n                timestamp TEXT NOT NULL,\n                data TEXT,\n                success BOOLEAN DEFAULT TRUE,\n                FOREIGN KEY (wallet_id) REFERENCES wallet_metadata_{chain_id} (wallet_id)\n            )\n        ')
        cursor.execute(f'\n            CREATE INDEX IF NOT EXISTS idx_wallet_events_{chain_id} \n            ON ledger_events_{chain_id} (wallet_id, timestamp)\n        ')
        cursor.execute(f'\n            CREATE INDEX IF NOT EXISTS idx_wallet_created_{chain_id} \n            ON wallet_metadata_{chain_id} (created_at)\n        ')
        conn.commit()

    def _get_connection(self, chain_id: str) -> sqlite3.Connection | None:
        """Get database connection for a specific chain"""
        _validate_chain_id(chain_id)
        if chain_id not in self.chain_connections:
            self._init_chain_database(chain_id)
        return self.chain_connections.get(chain_id)

    def _get_lock(self, chain_id: str) -> threading.Lock:
        """Get lock for a specific chain"""
        _validate_chain_id(chain_id)
        if chain_id not in self.chain_locks:
            self.chain_locks[chain_id] = threading.Lock()
        return self.chain_locks[chain_id]

    def create_wallet(self, chain_id: str, wallet_id: str, public_key: str, address: str | None=None, metadata: dict[str, str] | None=None) -> bool:
        """Create wallet in chain-specific database"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                logger.error('Invalid chain: %s', chain_id)
                return False
            conn = self._get_connection(chain_id)
            if not conn:
                return False
            lock = self._get_lock(chain_id)
            with lock:
                cursor = conn.cursor()
                cursor.execute(f'\n                    SELECT wallet_id FROM wallet_metadata_{chain_id} WHERE wallet_id = ?\n                ', (wallet_id,))
                if cursor.fetchone():
                    logger.warning('Wallet %s already exists in chain %s', wallet_id, chain_id)
                    return False
                now = datetime.now().isoformat()
                metadata_json = json.dumps(metadata or {})
                cursor.execute(f'\n                    INSERT INTO wallet_metadata_{chain_id} \n                    (wallet_id, public_key, address, metadata, created_at, updated_at)\n                    VALUES (?, ?, ?, ?, ?, ?)\n                ', (wallet_id, public_key, address, metadata_json, now, now))
                self.record_event(chain_id, wallet_id, 'created', {'public_key': public_key, 'address': address, 'metadata': metadata or {}})
                conn.commit()
                logger.info('Created wallet %s in chain %s', wallet_id, chain_id)
                return True
        except Exception as e:
            logger.error('Failed to create wallet %s in chain %s: %s', wallet_id, chain_id, e)
            return False

    def get_wallet(self, chain_id: str, wallet_id: str) -> ChainWalletMetadata | None:
        """Get wallet metadata from chain-specific database"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return None
            conn = self._get_connection(chain_id)
            if not conn:
                return None
            lock = self._get_lock(chain_id)
            with lock:
                cursor = conn.cursor()
                cursor.execute(f'\n                    SELECT wallet_id, public_key, address, metadata, created_at, updated_at\n                    FROM wallet_metadata_{chain_id} WHERE wallet_id = ?\n                ', (wallet_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                metadata = json.loads(row[3]) if row[3] else {}
                return ChainWalletMetadata(chain_id=chain_id, wallet_id=row[0], public_key=row[1], address=row[2], metadata=metadata, created_at=datetime.fromisoformat(row[4]), updated_at=datetime.fromisoformat(row[5]))
        except Exception as e:
            logger.error('Failed to get wallet %s from chain %s: %s', wallet_id, chain_id, e)
            return None

    def list_wallets(self, chain_id: str) -> list[ChainWalletMetadata]:
        """List all wallets in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return []
            conn = self._get_connection(chain_id)
            if not conn:
                return []
            lock = self._get_lock(chain_id)
            with lock:
                cursor = conn.cursor()
                cursor.execute(f'\n                    SELECT wallet_id, public_key, address, metadata, created_at, updated_at\n                    FROM wallet_metadata_{chain_id} ORDER BY created_at DESC\n                ')
                wallets = []
                for row in cursor.fetchall():
                    metadata = json.loads(row[3]) if row[3] else {}
                    wallets.append(ChainWalletMetadata(chain_id=chain_id, wallet_id=row[0], public_key=row[1], address=row[2], metadata=metadata, created_at=datetime.fromisoformat(row[4]), updated_at=datetime.fromisoformat(row[5])))
                return wallets
        except Exception as e:
            logger.error('Failed to list wallets in chain %s: %s', chain_id, e)
            return []

    def record_event(self, chain_id: str, wallet_id: str, event_type: str, data: dict[str, Any], success: bool=True) -> bool:
        """Record an event for a wallet in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return False
            conn = self._get_connection(chain_id)
            if not conn:
                return False
            lock = self._get_lock(chain_id)
            with lock:
                cursor = conn.cursor()
                cursor.execute(f'\n                    INSERT INTO ledger_events_{chain_id} \n                    (wallet_id, event_type, timestamp, data, success)\n                    VALUES (?, ?, ?, ?, ?)\n                ', (wallet_id, event_type, datetime.now().isoformat(), json.dumps(data), success))
                conn.commit()
                return True
        except Exception as e:
            logger.error('Failed to record event for wallet %s in chain %s: %s', wallet_id, chain_id, e)
            return False

    def get_wallet_events(self, chain_id: str, wallet_id: str, event_type: str | None=None, limit: int=100) -> list[ChainLedgerRecord]:
        """Get events for a wallet in a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return []
            conn = self._get_connection(chain_id)
            if not conn:
                return []
            lock = self._get_lock(chain_id)
            with lock:
                cursor = conn.cursor()
                if event_type:
                    cursor.execute(f'\n                        SELECT wallet_id, event_type, timestamp, data, success\n                        FROM ledger_events_{chain_id} \n                        WHERE wallet_id = ? AND event_type = ?\n                        ORDER BY timestamp DESC LIMIT ?\n                    ', (wallet_id, event_type, limit))
                else:
                    cursor.execute(f'\n                        SELECT wallet_id, event_type, timestamp, data, success\n                        FROM ledger_events_{chain_id} \n                        WHERE wallet_id = ?\n                        ORDER BY timestamp DESC LIMIT ?\n                    ', (wallet_id, limit))
                events = []
                for row in cursor.fetchall():
                    data = json.loads(row[3]) if row[3] else {}
                    events.append(ChainLedgerRecord(chain_id=chain_id, wallet_id=row[0], event_type=row[1], timestamp=datetime.fromisoformat(row[2]), data=data, success=row[4]))
                return events
        except Exception as e:
            logger.error('Failed to get events for wallet %s in chain %s: %s', wallet_id, chain_id, e)
            return []

    def get_chain_stats(self, chain_id: str) -> dict[str, Any]:
        """Get statistics for a specific chain"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                return {}
            conn = self._get_connection(chain_id)
            if not conn:
                return {}
            lock = self._get_lock(chain_id)
            with lock:
                cursor = conn.cursor()
                cursor.execute(f'SELECT COUNT(*) FROM wallet_metadata_{chain_id}')
                wallet_count = cursor.fetchone()[0]
                cursor.execute(f'\n                    SELECT event_type, COUNT(*) FROM ledger_events_{chain_id} \n                    GROUP BY event_type\n                ')
                event_counts = dict(cursor.fetchall())
                cursor.execute(f"\n                    SELECT COUNT(*) FROM ledger_events_{chain_id} \n                    WHERE timestamp > datetime('now', '-1 hour')\n                ")
                recent_activity = cursor.fetchone()[0]
                return {'chain_id': chain_id, 'wallet_count': wallet_count, 'event_counts': event_counts, 'recent_activity': recent_activity, 'database_path': str(self._get_chain_db_path(chain_id))}
        except Exception as e:
            logger.error('Failed to get stats for chain %s: %s', chain_id, e)
            return {}

    def get_all_chain_stats(self) -> dict[str, Any]:
        """Get statistics for all chains"""
        stats: dict[str, Any] = {'total_chains': 0, 'total_wallets': 0, 'chain_stats': {}}
        for chain in self.chain_manager.get_active_chains():
            chain_stats = self.get_chain_stats(chain.chain_id)
            if chain_stats:
                stats['chain_stats'][chain.chain_id] = chain_stats
                stats['total_wallets'] += chain_stats.get('wallet_count', 0)
                stats['total_chains'] += 1
        return stats

    def close_all_connections(self) -> None:
        """Close all database connections"""
        for chain_id, conn in self.chain_connections.items():
            try:
                conn.close()
                logger.info('Closed connection for chain: %s', chain_id)
            except Exception as e:
                logger.error('Failed to close connection for chain %s: %s', chain_id, e)
        self.chain_connections.clear()
        self.chain_locks.clear()
