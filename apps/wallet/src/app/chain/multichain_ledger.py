"""
Multi-Chain Ledger Adapter for Wallet Daemon

Chain-specific storage and ledger management for wallet operations
across multiple blockchain networks.
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
import sqlite3
import threading
import json
from datetime import datetime
from dataclasses import dataclass, asdict
import logging

from .manager import ChainManager, ChainConfig

logger = logging.getLogger(__name__)


@dataclass
class ChainLedgerRecord:
    """Chain-specific ledger record"""
    chain_id: str
    wallet_id: str
    event_type: str
    timestamp: datetime
    data: Dict[str, Any]
    success: bool = True


@dataclass
class ChainWalletMetadata:
    """Chain-specific wallet metadata"""
    chain_id: str
    wallet_id: str
    public_key: str
    address: Optional[str]
    metadata: Dict[str, str]
    created_at: datetime
    updated_at: datetime


class MultiChainLedgerAdapter:
    """Multi-chain ledger adapter with chain-specific storage"""
    
    def __init__(self, chain_manager: ChainManager, base_data_path: Optional[Path] = None):
        self.chain_manager = chain_manager
        self.base_data_path = base_data_path or Path("./data")
        self.base_data_path.mkdir(parents=True, exist_ok=True)
        
        # Separate database connections per chain
        self.chain_connections: Dict[str, sqlite3.Connection] = {}
        self.chain_locks: Dict[str, threading.Lock] = {}
        
        # Initialize databases for all chains
        self._initialize_chain_databases()
    
    def _initialize_chain_databases(self):
        """Initialize database for each chain"""
        for chain in self.chain_manager.list_chains():
            self._init_chain_database(chain.chain_id)
    
    def _get_chain_db_path(self, chain_id: str) -> Path:
        """Get database path for a specific chain"""
        chain = self.chain_manager.get_chain(chain_id)
        if chain and chain.ledger_db_path:
            return Path(chain.ledger_db_path)
        
        # Default path based on chain ID
        return self.base_data_path / f"wallet_ledger_{chain_id}.db"
    
    def _init_chain_database(self, chain_id: str):
        """Initialize database for a specific chain"""
        try:
            db_path = self._get_chain_db_path(chain_id)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create connection and lock for this chain
            conn = sqlite3.connect(db_path)
            self.chain_connections[chain_id] = conn
            self.chain_locks[chain_id] = threading.Lock()
            
            # Initialize schema
            with self.chain_locks[chain_id]:
                self._create_chain_schema(conn, chain_id)
            
            logger.info(f"Initialized database for chain: {chain_id}")
        except Exception as e:
            logger.error(f"Failed to initialize database for chain {chain_id}: {e}")
    
    def _create_chain_schema(self, conn: sqlite3.Connection, chain_id: str):
        """Create database schema for a specific chain"""
        cursor = conn.cursor()
        
        # Wallet metadata table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS wallet_metadata_{chain_id} (
                wallet_id TEXT PRIMARY KEY,
                public_key TEXT NOT NULL,
                address TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Ledger events table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS ledger_events_{chain_id} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                data TEXT,
                success BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (wallet_id) REFERENCES wallet_metadata_{chain_id} (wallet_id)
            )
        """)
        
        # Chain-specific indexes
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_wallet_events_{chain_id} 
            ON ledger_events_{chain_id} (wallet_id, timestamp)
        """)
        
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_wallet_created_{chain_id} 
            ON wallet_metadata_{chain_id} (created_at)
        """)
        
        conn.commit()
    
    def _get_connection(self, chain_id: str) -> Optional[sqlite3.Connection]:
        """Get database connection for a specific chain"""
        if chain_id not in self.chain_connections:
            self._init_chain_database(chain_id)
        
        return self.chain_connections.get(chain_id)
    
    def _get_lock(self, chain_id: str) -> threading.Lock:
        """Get lock for a specific chain"""
        if chain_id not in self.chain_locks:
            self.chain_locks[chain_id] = threading.Lock()
        
        return self.chain_locks[chain_id]
    
    def create_wallet(self, chain_id: str, wallet_id: str, public_key: str, 
                     address: Optional[str] = None, metadata: Optional[Dict[str, str]] = None) -> bool:
        """Create wallet in chain-specific database"""
        try:
            if not self.chain_manager.validate_chain_id(chain_id):
                logger.error(f"Invalid chain: {chain_id}")
                return False
            
            conn = self._get_connection(chain_id)
            if not conn:
                return False
            
            lock = self._get_lock(chain_id)
            with lock:
                cursor = conn.cursor()
                
                # Check if wallet already exists
                cursor.execute(f"""
                    SELECT wallet_id FROM wallet_metadata_{chain_id} WHERE wallet_id = ?
                """, (wallet_id,))
                
                if cursor.fetchone():
                    logger.warning(f"Wallet {wallet_id} already exists in chain {chain_id}")
                    return False
                
                # Insert wallet metadata
                now = datetime.now().isoformat()
                metadata_json = json.dumps(metadata or {})
                
                cursor.execute(f"""
                    INSERT INTO wallet_metadata_{chain_id} 
                    (wallet_id, public_key, address, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (wallet_id, public_key, address, metadata_json, now, now))
                
                # Record creation event
                self.record_event(chain_id, wallet_id, "created", {
                    "public_key": public_key,
                    "address": address,
                    "metadata": metadata or {}
                })
                
                conn.commit()
                logger.info(f"Created wallet {wallet_id} in chain {chain_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to create wallet {wallet_id} in chain {chain_id}: {e}")
            return False
    
    def get_wallet(self, chain_id: str, wallet_id: str) -> Optional[ChainWalletMetadata]:
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
                
                cursor.execute(f"""
                    SELECT wallet_id, public_key, address, metadata, created_at, updated_at
                    FROM wallet_metadata_{chain_id} WHERE wallet_id = ?
                """, (wallet_id,))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                metadata = json.loads(row[3]) if row[3] else {}
                
                return ChainWalletMetadata(
                    chain_id=chain_id,
                    wallet_id=row[0],
                    public_key=row[1],
                    address=row[2],
                    metadata=metadata,
                    created_at=datetime.fromisoformat(row[4]),
                    updated_at=datetime.fromisoformat(row[5])
                )
                
        except Exception as e:
            logger.error(f"Failed to get wallet {wallet_id} from chain {chain_id}: {e}")
            return None
    
    def list_wallets(self, chain_id: str) -> List[ChainWalletMetadata]:
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
                
                cursor.execute(f"""
                    SELECT wallet_id, public_key, address, metadata, created_at, updated_at
                    FROM wallet_metadata_{chain_id} ORDER BY created_at DESC
                """)
                
                wallets = []
                for row in cursor.fetchall():
                    metadata = json.loads(row[3]) if row[3] else {}
                    
                    wallets.append(ChainWalletMetadata(
                        chain_id=chain_id,
                        wallet_id=row[0],
                        public_key=row[1],
                        address=row[2],
                        metadata=metadata,
                        created_at=datetime.fromisoformat(row[4]),
                        updated_at=datetime.fromisoformat(row[5])
                    ))
                
                return wallets
                
        except Exception as e:
            logger.error(f"Failed to list wallets in chain {chain_id}: {e}")
            return []
    
    def record_event(self, chain_id: str, wallet_id: str, event_type: str, 
                     data: Dict[str, Any], success: bool = True) -> bool:
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
                
                # Insert event
                cursor.execute(f"""
                    INSERT INTO ledger_events_{chain_id} 
                    (wallet_id, event_type, timestamp, data, success)
                    VALUES (?, ?, ?, ?, ?)
                """, (wallet_id, event_type, datetime.now().isoformat(), 
                      json.dumps(data), success))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Failed to record event for wallet {wallet_id} in chain {chain_id}: {e}")
            return False
    
    def get_wallet_events(self, chain_id: str, wallet_id: str, 
                        event_type: Optional[str] = None, limit: int = 100) -> List[ChainLedgerRecord]:
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
                    cursor.execute(f"""
                        SELECT wallet_id, event_type, timestamp, data, success
                        FROM ledger_events_{chain_id} 
                        WHERE wallet_id = ? AND event_type = ?
                        ORDER BY timestamp DESC LIMIT ?
                    """, (wallet_id, event_type, limit))
                else:
                    cursor.execute(f"""
                        SELECT wallet_id, event_type, timestamp, data, success
                        FROM ledger_events_{chain_id} 
                        WHERE wallet_id = ?
                        ORDER BY timestamp DESC LIMIT ?
                    """, (wallet_id, limit))
                
                events = []
                for row in cursor.fetchall():
                    data = json.loads(row[3]) if row[3] else {}
                    
                    events.append(ChainLedgerRecord(
                        chain_id=chain_id,
                        wallet_id=row[0],
                        event_type=row[1],
                        timestamp=datetime.fromisoformat(row[2]),
                        data=data,
                        success=row[4]
                    ))
                
                return events
                
        except Exception as e:
            logger.error(f"Failed to get events for wallet {wallet_id} in chain {chain_id}: {e}")
            return []
    
    def get_chain_stats(self, chain_id: str) -> Dict[str, Any]:
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
                
                # Wallet count
                cursor.execute(f"SELECT COUNT(*) FROM wallet_metadata_{chain_id}")
                wallet_count = cursor.fetchone()[0]
                
                # Event count by type
                cursor.execute(f"""
                    SELECT event_type, COUNT(*) FROM ledger_events_{chain_id} 
                    GROUP BY event_type
                """)
                event_counts = dict(cursor.fetchall())
                
                # Recent activity
                cursor.execute(f"""
                    SELECT COUNT(*) FROM ledger_events_{chain_id} 
                    WHERE timestamp > datetime('now', '-1 hour')
                """)
                recent_activity = cursor.fetchone()[0]
                
                return {
                    "chain_id": chain_id,
                    "wallet_count": wallet_count,
                    "event_counts": event_counts,
                    "recent_activity": recent_activity,
                    "database_path": str(self._get_chain_db_path(chain_id))
                }
                
        except Exception as e:
            logger.error(f"Failed to get stats for chain {chain_id}: {e}")
            return {}
    
    def get_all_chain_stats(self) -> Dict[str, Any]:
        """Get statistics for all chains"""
        stats = {
            "total_chains": 0,
            "total_wallets": 0,
            "chain_stats": {}
        }
        
        for chain in self.chain_manager.get_active_chains():
            chain_stats = self.get_chain_stats(chain.chain_id)
            if chain_stats:
                stats["chain_stats"][chain.chain_id] = chain_stats
                stats["total_wallets"] += chain_stats.get("wallet_count", 0)
                stats["total_chains"] += 1
        
        return stats
    
    def close_all_connections(self):
        """Close all database connections"""
        for chain_id, conn in self.chain_connections.items():
            try:
                conn.close()
                logger.info(f"Closed connection for chain: {chain_id}")
            except Exception as e:
                logger.error(f"Failed to close connection for chain {chain_id}: {e}")
        
        self.chain_connections.clear()
        self.chain_locks.clear()
