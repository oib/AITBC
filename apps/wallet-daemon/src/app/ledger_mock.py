"""
SQLite Ledger Adapter for Wallet Daemon
Production-ready ledger implementation (replacing missing mock)
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class LedgerRecord:
    """Ledger record for wallet events"""
    wallet_id: str
    event_type: str
    timestamp: datetime
    data: Dict[str, Any]
    success: bool = True


@dataclass
class WalletMetadata:
    """Wallet metadata stored in ledger"""
    wallet_id: str
    public_key: str
    metadata: Dict[str, str]
    created_at: datetime
    updated_at: datetime


class SQLiteLedgerAdapter:
    """Production-ready SQLite ledger adapter"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path("./data/wallet_ledger.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                # Create wallet metadata table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS wallet_metadata (
                        wallet_id TEXT PRIMARY KEY,
                        public_key TEXT NOT NULL,
                        metadata TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                
                # Create events table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS wallet_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        wallet_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        data TEXT NOT NULL,
                        success INTEGER NOT NULL,
                        FOREIGN KEY (wallet_id) REFERENCES wallet_metadata (wallet_id)
                    )
                """)
                
                # Create indexes for performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_wallet_id ON wallet_events(wallet_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON wallet_events(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON wallet_events(event_type)")
                
                conn.commit()
            finally:
                conn.close()
    
    def upsert_wallet(self, wallet_id: str, public_key: str, metadata: Dict[str, str]) -> None:
        """Insert or update wallet metadata"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                now = datetime.utcnow().isoformat()
                metadata_json = json.dumps(metadata)
                
                # Try update first
                cursor = conn.execute("""
                    UPDATE wallet_metadata 
                    SET public_key = ?, metadata = ?, updated_at = ?
                    WHERE wallet_id = ?
                """, (public_key, metadata_json, now, wallet_id))
                
                # If no rows updated, insert new
                if cursor.rowcount == 0:
                    conn.execute("""
                        INSERT INTO wallet_metadata (wallet_id, public_key, metadata, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (wallet_id, public_key, metadata_json, now, now))
                
                conn.commit()
            finally:
                conn.close()
    
    def get_wallet(self, wallet_id: str) -> Optional[WalletMetadata]:
        """Get wallet metadata"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute("""
                    SELECT wallet_id, public_key, metadata, created_at, updated_at
                    FROM wallet_metadata
                    WHERE wallet_id = ?
                """, (wallet_id,))
                
                row = cursor.fetchone()
                if row:
                    metadata = json.loads(row[2])
                    return WalletMetadata(
                        wallet_id=row[0],
                        public_key=row[1],
                        metadata=metadata,
                        created_at=datetime.fromisoformat(row[3]),
                        updated_at=datetime.fromisoformat(row[4])
                    )
                return None
            finally:
                conn.close()
    
    def record_event(self, wallet_id: str, event_type: str, data: Dict[str, Any]) -> None:
        """Record a wallet event"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                now = datetime.utcnow().isoformat()
                data_json = json.dumps(data)
                success = data.get("success", True)
                
                conn.execute("""
                    INSERT INTO wallet_events (wallet_id, event_type, timestamp, data, success)
                    VALUES (?, ?, ?, ?, ?)
                """, (wallet_id, event_type, now, data_json, int(success)))
                
                conn.commit()
            finally:
                conn.close()
    
    def get_wallet_events(self, wallet_id: str, limit: int = 50) -> List[LedgerRecord]:
        """Get events for a wallet"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute("""
                    SELECT wallet_id, event_type, timestamp, data, success
                    FROM wallet_events
                    WHERE wallet_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (wallet_id, limit))
                
                events = []
                for row in cursor.fetchall():
                    data = json.loads(row[3])
                    events.append(LedgerRecord(
                        wallet_id=row[0],
                        event_type=row[1],
                        timestamp=datetime.fromisoformat(row[2]),
                        data=data,
                        success=bool(row[4])
                    ))
                
                return events
            finally:
                conn.close()
    
    def get_all_wallets(self) -> List[WalletMetadata]:
        """Get all wallets"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute("""
                    SELECT wallet_id, public_key, metadata, created_at, updated_at
                    FROM wallet_metadata
                    ORDER BY created_at DESC
                """)
                
                wallets = []
                for row in cursor.fetchall():
                    metadata = json.loads(row[2])
                    wallets.append(WalletMetadata(
                        wallet_id=row[0],
                        public_key=row[1],
                        metadata=metadata,
                        created_at=datetime.fromisoformat(row[3]),
                        updated_at=datetime.fromisoformat(row[4])
                    ))
                
                return wallets
            finally:
                conn.close()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get ledger statistics"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                # Wallet count
                wallet_count = conn.execute("SELECT COUNT(*) FROM wallet_metadata").fetchone()[0]
                
                # Event counts by type
                event_stats = conn.execute("""
                    SELECT event_type, COUNT(*) as count
                    FROM wallet_events
                    GROUP BY event_type
                """).fetchall()
                
                # Recent activity
                recent_events = conn.execute("""
                    SELECT COUNT(*) FROM wallet_events
                    WHERE timestamp > datetime('now', '-24 hours')
                """).fetchone()[0]
                
                return {
                    "total_wallets": wallet_count,
                    "event_breakdown": dict(event_stats),
                    "events_last_24h": recent_events,
                    "database_path": str(self.db_path)
                }
            finally:
                conn.close()
    
    def delete_wallet(self, wallet_id: str) -> bool:
        """Delete a wallet and all its events"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                # Delete events first (foreign key constraint)
                conn.execute("DELETE FROM wallet_events WHERE wallet_id = ?", (wallet_id,))
                
                # Delete wallet metadata
                cursor = conn.execute("DELETE FROM wallet_metadata WHERE wallet_id = ?", (wallet_id,))
                
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()
    
    def backup_ledger(self, backup_path: Path) -> bool:
        """Create a backup of the ledger database"""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                backup_conn = sqlite3.connect(backup_path)
                conn.backup(backup_conn)
                conn.close()
                backup_conn.close()
            return True
        except Exception:
            return False
    
    def verify_integrity(self) -> Dict[str, Any]:
        """Verify database integrity"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                # Run integrity check
                result = conn.execute("PRAGMA integrity_check").fetchall()
                
                # Check foreign key constraints
                fk_check = conn.execute("PRAGMA foreign_key_check").fetchall()
                
                return {
                    "integrity_check": result,
                    "foreign_key_check": fk_check,
                    "is_valid": len(result) == 1 and result[0][0] == "ok"
                }
            finally:
                conn.close()
