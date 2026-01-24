"""PostgreSQL adapter for Wallet Daemon"""

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

class PostgreSQLLedgerAdapter:
    """PostgreSQL implementation of the wallet ledger"""
    
    def __init__(self, db_config: Dict[str, Any]):
        self.db_config = db_config
        self.connection = None
        self._connect()
    
    def _connect(self):
        """Establish database connection"""
        try:
            self.connection = psycopg2.connect(
                cursor_factory=RealDictCursor,
                **self.db_config
            )
            logger.info("Connected to PostgreSQL wallet ledger")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
    
    def create_wallet(self, wallet_id: str, public_key: str, metadata: Dict[str, Any] = None) -> bool:
        """Create a new wallet"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO wallets (wallet_id, public_key, metadata)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (wallet_id) DO UPDATE
                    SET public_key = EXCLUDED.public_key,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                """, (wallet_id, public_key, json.dumps(metadata or {})))
                
                self.connection.commit()
                logger.info(f"Created wallet: {wallet_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to create wallet {wallet_id}: {e}")
            self.connection.rollback()
            return False
    
    def get_wallet(self, wallet_id: str) -> Optional[Dict[str, Any]]:
        """Get wallet information"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT wallet_id, public_key, metadata, created_at, updated_at
                    FROM wallets
                    WHERE wallet_id = %s
                """, (wallet_id,))
                
                result = cursor.fetchone()
                if result:
                    return dict(result)
                return None
        except Exception as e:
            logger.error(f"Failed to get wallet {wallet_id}: {e}")
            return None
    
    def list_wallets(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List all wallets"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT wallet_id, public_key, metadata, created_at, updated_at
                    FROM wallets
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (limit, offset))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to list wallets: {e}")
            return []
    
    def add_wallet_event(self, wallet_id: str, event_type: str, payload: Dict[str, Any]) -> bool:
        """Add an event to the wallet"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO wallet_events (wallet_id, event_type, payload)
                    VALUES (%s, %s, %s)
                """, (wallet_id, event_type, json.dumps(payload)))
                
                self.connection.commit()
                logger.debug(f"Added event {event_type} to wallet {wallet_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to add event to wallet {wallet_id}: {e}")
            self.connection.rollback()
            return False
    
    def get_wallet_events(self, wallet_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get events for a wallet"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT id, event_type, payload, created_at
                    FROM wallet_events
                    WHERE wallet_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (wallet_id, limit))
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get events for wallet {wallet_id}: {e}")
            return []
    
    def update_wallet_metadata(self, wallet_id: str, metadata: Dict[str, Any]) -> bool:
        """Update wallet metadata"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE wallets
                    SET metadata = %s, updated_at = NOW()
                    WHERE wallet_id = %s
                """, (json.dumps(metadata), wallet_id))
                
                self.connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update metadata for wallet {wallet_id}: {e}")
            self.connection.rollback()
            return False
    
    def delete_wallet(self, wallet_id: str) -> bool:
        """Delete a wallet and all its events"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM wallets
                    WHERE wallet_id = %s
                """, (wallet_id,))
                
                self.connection.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete wallet {wallet_id}: {e}")
            self.connection.rollback()
            return False
    
    def get_wallet_stats(self) -> Dict[str, Any]:
        """Get wallet statistics"""
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as total_wallets FROM wallets")
                total_wallets = cursor.fetchone()['total_wallets']
                
                cursor.execute("SELECT COUNT(*) as total_events FROM wallet_events")
                total_events = cursor.fetchone()['total_events']
                
                cursor.execute("""
                    SELECT event_type, COUNT(*) as count
                    FROM wallet_events
                    GROUP BY event_type
                    ORDER BY count DESC
                """)
                event_types = {row['event_type']: row['count'] for row in cursor.fetchall()}
                
                return {
                    "total_wallets": total_wallets,
                    "total_events": total_events,
                    "event_types": event_types
                }
        except Exception as e:
            logger.error(f"Failed to get wallet stats: {e}")
            return {}
    
    def close(self):
        """Close the database connection"""
        if self.connection:
            self.connection.close()
            logger.info("PostgreSQL connection closed")

# Factory function
def create_postgresql_adapter() -> PostgreSQLLedgerAdapter:
    """Create a PostgreSQL ledger adapter"""
    config = {
        "host": "localhost",
        "database": "aitbc_wallet",
        "user": "aitbc_user",
        "password": "aitbc_password",
        "port": 5432
    }
    return PostgreSQLLedgerAdapter(config)
