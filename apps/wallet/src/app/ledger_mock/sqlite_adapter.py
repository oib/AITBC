from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class WalletRecord:
    wallet_id: str
    public_key: str
    metadata: dict


@dataclass
class WalletEvent:
    wallet_id: str
    event_type: str
    payload: dict


class SQLiteLedgerAdapter:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS wallets (
                    wallet_id TEXT PRIMARY KEY,
                    public_key TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS wallet_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wallet_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(wallet_id) REFERENCES wallets(wallet_id)
                )
                """
            )

    def upsert_wallet(self, wallet_id: str, public_key: str, metadata: dict) -> None:
        payload = json.dumps(metadata)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO wallets(wallet_id, public_key, metadata)
                VALUES (?, ?, ?)
                ON CONFLICT(wallet_id) DO UPDATE SET public_key=excluded.public_key, metadata=excluded.metadata
                """,
                (wallet_id, public_key, payload),
            )

    def get_wallet(self, wallet_id: str) -> Optional[WalletRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT wallet_id, public_key, metadata FROM wallets WHERE wallet_id = ?",
                (wallet_id,),
            ).fetchone()
        if row is None:
            return None
        return WalletRecord(wallet_id=row["wallet_id"], public_key=row["public_key"], metadata=json.loads(row["metadata"]))

    def list_wallets(self) -> Iterable[WalletRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT wallet_id, public_key, metadata FROM wallets").fetchall()
        for row in rows:
            yield WalletRecord(wallet_id=row["wallet_id"], public_key=row["public_key"], metadata=json.loads(row["metadata"]))

    def record_event(self, wallet_id: str, event_type: str, payload: dict) -> None:
        data = json.dumps(payload)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO wallet_events(wallet_id, event_type, payload) VALUES (?, ?, ?)",
                (wallet_id, event_type, data),
            )

    def list_events(self, wallet_id: str) -> Iterable[WalletEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT wallet_id, event_type, payload FROM wallet_events WHERE wallet_id = ? ORDER BY id",
                (wallet_id,),
            ).fetchall()
        for row in rows:
            yield WalletEvent(
                wallet_id=row["wallet_id"],
                event_type=row["event_type"],
                payload=json.loads(row["payload"]),
            )
