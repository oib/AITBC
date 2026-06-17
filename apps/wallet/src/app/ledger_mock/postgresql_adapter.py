"""PostgreSQL adapter for Wallet Daemon"""

import json
from typing import Any, cast

import psycopg2
from psycopg2 import extensions
from psycopg2.extras import RealDictCursor

from aitbc.aitbc_logging import get_logger

logger = get_logger(__name__)


class PostgreSQLLedgerAdapter:
    """PostgreSQL implementation of the wallet ledger"""

    def __init__(self, db_config: dict[str, Any]):
        self.db_config = db_config
        self.connection: extensions.connection | None = None
        self._connect()

    def _connect(self) -> None:
        """Establish database connection"""
        try:
            self.connection = psycopg2.connect(cursor_factory=RealDictCursor, **self.db_config)
            logger.info("Connected to PostgreSQL wallet ledger")
        except Exception as e:
            logger.error("Failed to connect to PostgreSQL: %s", e)
            raise

    def create_wallet(self, wallet_id: str, public_key: str, metadata: dict[str, Any] | None = None) -> bool:
        """Create a new wallet"""
        try:
            assert self.connection is not None
            cursor = cast(extensions.cursor, self.connection.cursor(cursor_factory=RealDictCursor))
            cursor.execute(
                "\n                    INSERT INTO wallets (wallet_id, public_key, metadata)\n                    VALUES (%s, %s, %s)\n                    ON CONFLICT (wallet_id) DO UPDATE\n                    SET public_key = EXCLUDED.public_key,\n                        metadata = EXCLUDED.metadata,\n                        updated_at = NOW()\n                ",
                (wallet_id, public_key, json.dumps(metadata or {})),
            )
            self.connection.commit()
            cursor.close()
            logger.info("Created wallet: %s", wallet_id)
            return True
        except Exception as e:
            logger.error("Failed to create wallet %s: %s", wallet_id, e)
            if self.connection:
                self.connection.rollback()
            return False

    def get_wallet(self, wallet_id: str) -> dict[str, Any] | None:
        """Get wallet information"""
        try:
            assert self.connection is not None
            cursor = cast(extensions.cursor, self.connection.cursor(cursor_factory=RealDictCursor))
            cursor.execute(
                "\n                    SELECT wallet_id, public_key, metadata, created_at, updated_at\n                    FROM wallets\n                    WHERE wallet_id = %s\n                ",
                (wallet_id,),
            )
            result = cursor.fetchone()
            cursor.close()
            if result:
                return dict(result)
            return None
        except Exception as e:
            logger.error("Failed to get wallet %s: %s", wallet_id, e)
            return None

    def list_wallets(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """List all wallets"""
        try:
            assert self.connection is not None
            cursor = cast(extensions.cursor, self.connection.cursor(cursor_factory=RealDictCursor))
            cursor.execute(
                "\n                    SELECT wallet_id, public_key, metadata, created_at, updated_at\n                    FROM wallets\n                    ORDER BY created_at DESC\n                    LIMIT %s OFFSET %s\n                ",
                (limit, offset),
            )
            result = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return result
        except Exception as e:
            logger.error("Failed to list wallets: %s", e)
            return []

    def add_wallet_event(self, wallet_id: str, event_type: str, payload: dict[str, Any]) -> bool:
        """Add an event to the wallet"""
        try:
            assert self.connection is not None
            cursor = cast(extensions.cursor, self.connection.cursor(cursor_factory=RealDictCursor))
            cursor.execute(
                "\n                    INSERT INTO wallet_events (wallet_id, event_type, payload)\n                    VALUES (%s, %s, %s)\n                ",
                (wallet_id, event_type, json.dumps(payload)),
            )
            self.connection.commit()
            cursor.close()
            logger.debug("Added event %s to wallet %s", event_type, wallet_id)
            return True
        except Exception as e:
            logger.error("Failed to add event to wallet %s: %s", wallet_id, e)
            if self.connection:
                self.connection.rollback()
            return False

    def get_wallet_events(self, wallet_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get events for a wallet"""
        try:
            assert self.connection is not None
            cursor = cast(extensions.cursor, self.connection.cursor(cursor_factory=RealDictCursor))
            cursor.execute(
                "\n                    SELECT id, event_type, payload, created_at\n                    FROM wallet_events\n                    WHERE wallet_id = %s\n                    ORDER BY created_at DESC\n                    LIMIT %s\n                ",
                (wallet_id, limit),
            )
            result = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            return result
        except Exception as e:
            logger.error("Failed to get events for wallet %s: %s", wallet_id, e)
            return []

    def update_wallet_metadata(self, wallet_id: str, metadata: dict[str, Any]) -> bool:
        """Update wallet metadata"""
        try:
            assert self.connection is not None
            cursor = cast(extensions.cursor, self.connection.cursor(cursor_factory=RealDictCursor))
            cursor.execute(
                "\n                    UPDATE wallets\n                    SET metadata = %s, updated_at = NOW()\n                    WHERE wallet_id = %s\n                ",
                (json.dumps(metadata), wallet_id),
            )
            self.connection.commit()
            result = cursor.rowcount > 0
            cursor.close()
            return result
        except Exception as e:
            logger.error("Failed to update metadata for wallet %s: %s", wallet_id, e)
            if self.connection:
                self.connection.rollback()
            return False

    def delete_wallet(self, wallet_id: str) -> bool:
        """Delete a wallet and all its events"""
        try:
            assert self.connection is not None
            cursor = cast(extensions.cursor, self.connection.cursor(cursor_factory=RealDictCursor))
            cursor.execute(
                "\n                    DELETE FROM wallets\n                    WHERE wallet_id = %s\n                ",
                (wallet_id,),
            )
            self.connection.commit()
            result = cursor.rowcount > 0
            cursor.close()
            return result
        except Exception as e:
            logger.error("Failed to delete wallet %s: %s", wallet_id, e)
            if self.connection:
                self.connection.rollback()
            return False

    def get_wallet_stats(self) -> dict[str, Any]:
        """Get wallet statistics"""
        try:
            assert self.connection is not None
            cursor = cast(extensions.cursor, self.connection.cursor(cursor_factory=RealDictCursor))
            cursor.execute("SELECT COUNT(*) as total_wallets FROM wallets")
            wallets_result = cast(dict[str, Any] | None, cursor.fetchone())
            total_wallets = wallets_result["total_wallets"] if wallets_result else 0
            cursor.execute("SELECT COUNT(*) as total_events FROM wallet_events")
            events_result = cast(dict[str, Any] | None, cursor.fetchone())
            total_events = events_result["total_events"] if events_result else 0
            cursor.execute(
                "\n                    SELECT event_type, COUNT(*) as count\n                    FROM wallet_events\n                    GROUP BY event_type\n                    ORDER BY count DESC\n                "
            )
            event_types = {
                cast(dict[str, Any], row)["event_type"]: cast(dict[str, Any], row)["count"] for row in cursor.fetchall()
            }
            cursor.close()
            return {"total_wallets": total_wallets, "total_events": total_events, "event_types": event_types}
        except Exception as e:
            logger.error("Failed to get wallet stats: %s", e)
            return {}

    def close(self) -> None:
        """Close the database connection"""
        if self.connection:
            self.connection.close()
            logger.info("PostgreSQL connection closed")


def create_postgresql_adapter() -> PostgreSQLLedgerAdapter:
    """Create a PostgreSQL ledger adapter"""
    config = {
        "host": "localhost",
        "database": "aitbc_wallet",
        "user": "aitbc_user",
        "password": "aitbc_password",
        "port": 5432,
    }
    return PostgreSQLLedgerAdapter(config)
