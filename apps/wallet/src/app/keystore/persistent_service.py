"""
Persistent Keystore Service - Fixes data loss on restart
Replaces the in-memory-only keystore with database persistence
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from secrets import token_bytes

from nacl.signing import SigningKey

from ..crypto.encryption import EncryptionSuite, EncryptionError
from ..security import validate_password_rules, wipe_buffer


@dataclass
class WalletRecord:
    """Wallet record with database persistence"""
    wallet_id: str
    public_key: str
    salt: bytes
    nonce: bytes
    ciphertext: bytes
    metadata: Dict[str, str]
    created_at: str
    updated_at: str


class PersistentKeystoreService:
    """Persistent keystore with database storage and proper encryption"""

    def __init__(self, db_path: Optional[Path] = None, encryption: Optional[EncryptionSuite] = None) -> None:
        self.db_path = db_path or Path("./data/keystore.db")
        # Resolve path to prevent directory traversal attacks
        self.db_path = self.db_path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._encryption = encryption or EncryptionSuite()
        self._lock = threading.Lock()
        self._init_database()

    def _init_database(self):
        """Initialize database schema"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS wallets (
                        wallet_id TEXT PRIMARY KEY,
                        public_key TEXT NOT NULL,
                        salt BLOB NOT NULL,
                        nonce BLOB NOT NULL,
                        ciphertext BLOB NOT NULL,
                        metadata TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS wallet_access_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        wallet_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        success INTEGER NOT NULL,
                        ip_address TEXT,
                        FOREIGN KEY (wallet_id) REFERENCES wallets (wallet_id)
                    )
                """)
                
                # Indexes for performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_wallets_created_at ON wallets(created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_access_log_wallet_id ON wallet_access_log(wallet_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_access_log_timestamp ON wallet_access_log(timestamp)")
                
                conn.commit()
            finally:
                conn.close()

    def list_wallets(self) -> List[str]:
        """List all wallet IDs"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute("SELECT wallet_id FROM wallets ORDER BY created_at DESC")
                return [row[0] for row in cursor.fetchall()]
            finally:
                conn.close()

    def list_records(self) -> Iterable[WalletRecord]:
        """List all wallet records"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute("""
                    SELECT wallet_id, public_key, salt, nonce, ciphertext, metadata, created_at, updated_at
                    FROM wallets
                    ORDER BY created_at DESC
                """)
                
                for row in cursor.fetchall():
                    metadata = json.loads(row[5])
                    yield WalletRecord(
                        wallet_id=row[0],
                        public_key=row[1],
                        salt=row[2],
                        nonce=row[3],
                        ciphertext=row[4],
                        metadata=metadata,
                        created_at=row[6],
                        updated_at=row[7]
                    )
            finally:
                conn.close()

    def get_wallet(self, wallet_id: str) -> Optional[WalletRecord]:
        """Get wallet record by ID"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute("""
                    SELECT wallet_id, public_key, salt, nonce, ciphertext, metadata, created_at, updated_at
                    FROM wallets
                    WHERE wallet_id = ?
                """, (wallet_id,))
                
                row = cursor.fetchone()
                if row:
                    metadata = json.loads(row[5])
                    return WalletRecord(
                        wallet_id=row[0],
                        public_key=row[1],
                        salt=row[2],
                        nonce=row[3],
                        ciphertext=row[4],
                        metadata=metadata,
                        created_at=row[6],
                        updated_at=row[7]
                    )
                return None
            finally:
                conn.close()

    def create_wallet(
        self,
        wallet_id: str,
        password: str,
        secret: Optional[bytes] = None,
        metadata: Optional[Dict[str, str]] = None,
        ip_address: Optional[str] = None
    ) -> WalletRecord:
        """Create a new wallet with database persistence"""
        with self._lock:
            # Check if wallet already exists
            if self.get_wallet(wallet_id):
                raise ValueError("wallet already exists")

            validate_password_rules(password)

            metadata_map = {str(k): str(v) for k, v in (metadata or {}).items()}

            if secret is None:
                signing_key = SigningKey.generate()
                secret_bytes = signing_key.encode()
            else:
                if len(secret) != SigningKey.seed_size:
                    raise ValueError("secret key must be 32 bytes")
                secret_bytes = secret
                signing_key = SigningKey(secret_bytes)

            salt = token_bytes(self._encryption.salt_bytes)
            nonce = token_bytes(self._encryption.nonce_bytes)
            ciphertext = self._encryption.encrypt(password=password, plaintext=secret_bytes, salt=salt, nonce=nonce)
            
            now = datetime.utcnow().isoformat()
            
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("""
                    INSERT INTO wallets (wallet_id, public_key, salt, nonce, ciphertext, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    wallet_id,
                    signing_key.verify_key.encode().hex(),
                    salt,
                    nonce,
                    ciphertext,
                    json.dumps(metadata_map),
                    now,
                    now
                ))
                
                # Log creation
                conn.execute("""
                    INSERT INTO wallet_access_log (wallet_id, action, timestamp, success, ip_address)
                    VALUES (?, ?, ?, ?, ?)
                """, (wallet_id, "created", now, 1, ip_address))
                
                conn.commit()
            finally:
                conn.close()

            record = WalletRecord(
                wallet_id=wallet_id,
                public_key=signing_key.verify_key.encode().hex(),
                salt=salt,
                nonce=nonce,
                ciphertext=ciphertext,
                metadata=metadata_map,
                created_at=now,
                updated_at=now
            )
            
            return record

    def unlock_wallet(self, wallet_id: str, password: str, ip_address: Optional[str] = None) -> bytes:
        """Unlock wallet and return secret key"""
        record = self.get_wallet(wallet_id)
        if record is None:
            self._log_access(wallet_id, "unlock_failed", False, ip_address)
            raise KeyError("wallet not found")
        
        try:
            secret = self._encryption.decrypt(password=password, ciphertext=record.ciphertext, salt=record.salt, nonce=record.nonce)
            self._log_access(wallet_id, "unlock_success", True, ip_address)
            return secret
        except EncryptionError as exc:
            self._log_access(wallet_id, "unlock_failed", False, ip_address)
            raise ValueError("failed to decrypt wallet") from exc

    def delete_wallet(self, wallet_id: str) -> bool:
        """Delete a wallet and all its access logs"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                # Delete access logs first
                conn.execute("DELETE FROM wallet_access_log WHERE wallet_id = ?", (wallet_id,))
                
                # Delete wallet
                cursor = conn.execute("DELETE FROM wallets WHERE wallet_id = ?", (wallet_id,))
                
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def sign_message(self, wallet_id: str, password: str, message: bytes, ip_address: Optional[str] = None) -> bytes:
        """Sign a message with wallet's private key"""
        try:
            secret_bytes = bytearray(self.unlock_wallet(wallet_id, password, ip_address))
            try:
                signing_key = SigningKey(bytes(secret_bytes))
                signed = signing_key.sign(message)
                self._log_access(wallet_id, "sign_success", True, ip_address)
                return signed.signature
            finally:
                wipe_buffer(secret_bytes)
        except (KeyError, ValueError) as exc:
            self._log_access(wallet_id, "sign_failed", False, ip_address)
            raise

    def update_metadata(self, wallet_id: str, metadata: Dict[str, str]) -> bool:
        """Update wallet metadata"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                now = datetime.utcnow().isoformat()
                metadata_json = json.dumps(metadata)
                
                cursor = conn.execute("""
                    UPDATE wallets 
                    SET metadata = ?, updated_at = ?
                    WHERE wallet_id = ?
                """, (metadata_json, now, wallet_id))
                
                conn.commit()
                return cursor.rowcount > 0
            finally:
                conn.close()

    def _log_access(self, wallet_id: str, action: str, success: bool, ip_address: Optional[str] = None):
        """Log wallet access for audit trail"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                now = datetime.utcnow().isoformat()
                conn.execute("""
                    INSERT INTO wallet_access_log (wallet_id, action, timestamp, success, ip_address)
                    VALUES (?, ?, ?, ?, ?)
                """, (wallet_id, action, now, int(success), ip_address))
                conn.commit()
            except Exception:
                # Don't fail the main operation if logging fails
                pass
            finally:
                conn.close()

    def get_access_log(self, wallet_id: str, limit: int = 50) -> List[Dict]:
        """Get access log for a wallet"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute("""
                    SELECT action, timestamp, success, ip_address
                    FROM wallet_access_log
                    WHERE wallet_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (wallet_id, limit))
                
                return [
                    {
                        "action": row[0],
                        "timestamp": row[1],
                        "success": bool(row[2]),
                        "ip_address": row[3]
                    }
                    for row in cursor.fetchall()
                ]
            finally:
                conn.close()

    def get_statistics(self) -> Dict[str, Any]:
        """Get keystore statistics"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                # Wallet count
                wallet_count = conn.execute("SELECT COUNT(*) FROM wallets").fetchone()[0]
                
                # Recent activity
                recent_creations = conn.execute("""
                    SELECT COUNT(*) FROM wallets
                    WHERE created_at > datetime('now', '-24 hours')
                """).fetchone()[0]
                
                recent_access = conn.execute("""
                    SELECT COUNT(*) FROM wallet_access_log
                    WHERE timestamp > datetime('now', '-24 hours')
                """).fetchone()[0]
                
                # Access success rate
                total_access = conn.execute("SELECT COUNT(*) FROM wallet_access_log").fetchone()[0]
                successful_access = conn.execute("SELECT COUNT(*) FROM wallet_access_log WHERE success = 1").fetchone()[0]
                
                success_rate = (successful_access / total_access * 100) if total_access > 0 else 0
                
                return {
                    "total_wallets": wallet_count,
                    "created_last_24h": recent_creations,
                    "access_last_24h": recent_access,
                    "access_success_rate": round(success_rate, 2),
                    "database_path": str(self.db_path)
                }
            finally:
                conn.close()

    def backup_keystore(self, backup_path: Path) -> bool:
        """Create a backup of the keystore database"""
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


# Import datetime for the module
from datetime import datetime
