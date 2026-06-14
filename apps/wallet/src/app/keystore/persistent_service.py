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
from typing import Any, Dict, Iterable, List, Optional
from secrets import token_bytes

import httpx
from nacl.signing import SigningKey

from ..crypto.encryption import EncryptionSuite, EncryptionError
from ..security import validate_password_rules, wipe_buffer
from ..settings import settings


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
        # SECURITY FIX: Validate path is within allowed directory to prevent directory traversal
        default_path = Path("./data/keystore.db").resolve()
        if db_path is None:
            self.db_path = default_path
        else:
            self.db_path = Path(db_path).resolve()
            # Ensure the resolved path is within allowed directories
            cwd = Path.cwd().resolve()
            allowed = [cwd, cwd / "data", Path("/var/lib/aitbc"), Path("/var/lib/aitbc/data")]
            if not any(str(self.db_path).startswith(str(a)) for a in allowed):
                raise ValueError(f"Invalid database path: {self.db_path}. Path must be within {allowed}")
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._encryption = encryption or EncryptionSuite()
        self._lock = threading.Lock()
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Lazy initialization of database"""
        if not self._initialized:
            self._init_database()
            self._initialized = True

    def _init_database(self) -> None:
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
        self._ensure_initialized()
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.execute("SELECT wallet_id FROM wallets ORDER BY created_at DESC")
                return [row[0] for row in cursor.fetchall()]
            finally:
                conn.close()

    def list_records(self) -> Iterable[WalletRecord]:
        """List all wallet records"""
        self._ensure_initialized()
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

    def _get_wallet_unlocked(self, wallet_id: str) -> Optional[WalletRecord]:
        """Get wallet record by ID (internal method, assumes caller holds lock)"""
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

    def get_wallet(self, wallet_id: str) -> Optional[WalletRecord]:
        """Get wallet record by ID"""
        self._ensure_initialized()
        with self._lock:
            return self._get_wallet_unlocked(wallet_id)

    def _register_account_on_chain(self, address: str) -> Dict:
        """Register the wallet address on the blockchain"""
        try:
            rpc_url = settings.blockchain_rpc_url
            response = httpx.post(
                f"{rpc_url}/rpc/register-account",
                json={"address": address},
                timeout=10.0
            )
            response.raise_for_status()
            result = response.json()
            return {
                "success": result.get("success", False),
                "created": result.get("created", False),
                "message": result.get("message", ""),
                "balance": result.get("balance", 0)
            }
        except Exception as e:
            # Log but don't fail - wallet is still created locally
            return {
                "success": False,
                "created": False,
                "message": f"Failed to register on chain: {str(e)}",
                "balance": 0
            }

    def create_wallet(
        self,
        wallet_id: str,
        password: str,
        secret: Optional[bytes] = None,
        metadata: Optional[Dict[str, str]] = None,
        ip_address: Optional[str] = None
    ) -> WalletRecord:
        """Create a new wallet with database persistence and blockchain registration"""
        self._ensure_initialized()
        with self._lock:
            # Check if wallet already exists (use unlocked version to avoid deadlock)
            if self._get_wallet_unlocked(wallet_id):
                raise ValueError("wallet already exists")

            validate_password_rules(password)

            metadata_map = {str(k): str(v) for k, v in (metadata or {}).items()}

            if secret is None:
                signing_key = SigningKey.generate()
                secret_bytes = signing_key.encode()
            else:
                if len(secret) != 32:
                    raise ValueError("secret key must be 32 bytes")
                secret_bytes = secret
                signing_key = SigningKey(secret_bytes)

            salt = token_bytes(self._encryption.salt_bytes)
            nonce = token_bytes(self._encryption.nonce_bytes)
            ciphertext = self._encryption.encrypt(password=password, plaintext=secret_bytes, salt=salt, nonce=nonce)
            
            public_key_hex = signing_key.verify_key.encode().hex()
            now = datetime.now(timezone.utc).isoformat()
            
            conn = sqlite3.connect(self.db_path)
            try:
                conn.execute("""
                    INSERT INTO wallets (wallet_id, public_key, salt, nonce, ciphertext, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    wallet_id,
                    public_key_hex,
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

            # Register account on blockchain
            chain_registration = self._register_account_on_chain(public_key_hex)
            if chain_registration["success"]:
                metadata_map["chain_registered"] = "true"
                metadata_map["chain_balance"] = str(chain_registration.get("balance", 0))
                if chain_registration.get("created"):
                    metadata_map["chain_status"] = "created"
                else:
                    metadata_map["chain_status"] = "existing"
            else:
                metadata_map["chain_registered"] = "false"
                metadata_map["chain_status"] = "pending"
                metadata_map["chain_error"] = chain_registration.get("message", "")

            record = WalletRecord(
                wallet_id=wallet_id,
                public_key=public_key_hex,
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

    def sign_and_submit_transaction(
        self,
        wallet_id: str,
        password: str,
        recipient: str,
        amount: int,
        fee: int = 1000,
        nonce: Optional[int] = None,
        chain_id: Optional[str] = None,
        payload: Optional[Dict] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sign and submit a transaction to the blockchain.
        
        Args:
            wallet_id: Sender wallet ID
            password: Wallet password
            recipient: Recipient address (hex)
            amount: Amount to transfer
            fee: Transaction fee (default 1000)
            nonce: Transaction nonce (auto-fetched if None)
            chain_id: Chain ID (uses default if None)
            payload: Optional transaction payload data
            ip_address: Client IP for logging
            
        Returns:
            Transaction result including tx_hash
        """
        record = self.get_wallet(wallet_id)
        if not record:
            raise KeyError(f"Wallet not found: {wallet_id}")
        
        sender_address = record.public_key
        
        try:
            # Unlock wallet to get signing key
            secret_bytes = bytearray(self.unlock_wallet(wallet_id, password, ip_address))
            try:
                signing_key = SigningKey(bytes(secret_bytes))
                
                # Fetch nonce from blockchain if not provided
                if nonce is None:
                    nonce = self._get_account_nonce(sender_address)
                
                # Ensure chain_id
                if chain_id is None:
                    chain_id = "ait-mainnet"
                
                # Normalize addresses
                sender = sender_address.lower().strip()
                recipient = recipient.lower().strip()
                if not recipient.startswith("0x"):
                    recipient = "0x" + recipient
                
                # Build transaction data
                tx_data = {
                    "from": sender,
                    "to": recipient,
                    "amount": amount,
                    "fee": fee,
                    "nonce": nonce,
                    "chain_id": chain_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": "TRANSFER"
                }
                
                # Add custom payload if provided
                if payload:
                    tx_data["payload"] = payload
                
                # Create canonical signing message
                message = json.dumps(tx_data, sort_keys=True, separators=(',', ':')).encode()
                
                # Sign with Ed25519
                signed = signing_key.sign(message)
                signature_hex = signed.signature.hex()
                
                # Submit to blockchain RPC
                result = self._submit_transaction_to_chain(tx_data, signature_hex)
                
                # Log success
                self._log_access(wallet_id, "transaction_submitted", True, ip_address)
                
                return {
                    "success": result.get("success", False),
                    "tx_hash": result.get("tx_hash"),
                    "status": result.get("status", "pending"),
                    "sender": sender,
                    "recipient": recipient,
                    "amount": amount,
                    "fee": fee,
                    "nonce": nonce,
                    "signature": signature_hex[:32] + "..."  # Truncated for security
                }
                
            finally:
                wipe_buffer(secret_bytes)
                
        except Exception as e:
            self._log_access(wallet_id, "transaction_failed", False, ip_address)
            return {
                "success": False,
                "error": str(e),
                "sender": sender_address,
                "recipient": recipient if 'recipient' in locals() else None
            }
    
    def _get_account_nonce(self, address: str) -> int:
        """Fetch current nonce from blockchain for an address"""
        try:
            rpc_url = settings.blockchain_rpc_url
            response = httpx.get(
                f"{rpc_url}/rpc/accounts/{address}",
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                return int(data.get("nonce", 0))
            return 0
        except Exception:
            # Default to 0 if account doesn't exist or request fails
            return 0
    
    def _submit_transaction_to_chain(self, tx_data: Dict, signature: str) -> Dict:
        """Submit signed transaction to blockchain RPC"""
        try:
            rpc_url = settings.blockchain_rpc_url
            
            # Build RPC request
            request_data = {
                "sender": tx_data["from"],
                "recipient": tx_data["to"],
                "amount": tx_data["amount"],
                "fee": tx_data["fee"],
                "nonce": tx_data["nonce"],
                "chain_id": tx_data["chain_id"],
                "sig": signature,
                "payload": tx_data.get("payload", {}),
                "type": tx_data.get("type", "TRANSFER")
            }
            
            response = httpx.post(
                f"{rpc_url}/rpc/transaction",
                json=request_data,
                timeout=30.0
            )
            response.raise_for_status()
            return dict(response.json())
            
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def update_metadata(self, wallet_id: str, metadata: Dict[str, str]) -> bool:
        """Update wallet metadata"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                now = datetime.now(timezone.utc).isoformat()
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

    def _log_access(self, wallet_id: str, action: str, success: bool, ip_address: Optional[str] = None) -> None:
        """Log wallet access for audit trail"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            try:
                now = datetime.now(timezone.utc).isoformat()
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
from datetime import datetime, timezone
