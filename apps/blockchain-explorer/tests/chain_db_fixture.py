"""Shared sqlite chain.db builders for explorer integration tests (#1285)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def create_chain_db(tmp_path: Path) -> Path:
    db_file = tmp_path / "chain.db"
    conn = sqlite3.connect(db_file)
    conn.execute(
        """CREATE TABLE block (
            height INTEGER, hash TEXT, proposer TEXT, timestamp TEXT,
            tx_count INTEGER, state_root TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE "transaction" (
            tx_hash TEXT, sender TEXT, recipient TEXT, payload TEXT,
            block_height INTEGER, created_at TEXT, type TEXT, status TEXT,
            value INTEGER, fee INTEGER, nonce INTEGER
        )"""
    )
    conn.commit()
    conn.close()
    return db_file


def insert_blocks(db_file: Path, count: int, *, with_txs: bool = False) -> None:
    conn = sqlite3.connect(db_file)
    for i in range(1, count + 1):
        conn.execute(
            "INSERT INTO block VALUES (?,?,?,?,?,?)",
            (i, f"0x{i:064x}", "0xproposer", f"2026-01-01 00:{i // 60:02d}:{i % 60:02d}", 1 if with_txs else 0, "0xroot"),
        )
        if with_txs:
            conn.execute(
                """INSERT INTO "transaction" VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"0x{i:064x}",
                    "0xsender",
                    "0xrecipient",
                    "{}",
                    i,
                    f"2026-01-01 00:{i // 60:02d}:{i % 60:02d}",
                    "TRANSFER",
                    "confirmed",
                    36_000_000,
                    1,
                    0,
                ),
            )
    conn.commit()
    conn.close()


def patch_chain_db(monkeypatch, db_file: Path) -> None:
    import chain_client
    import routers.analytics as analytics_router
    import routers.blocks as blocks_router
    import routers.transactions as transactions_router

    for module in (chain_client, analytics_router, blocks_router, transactions_router):
        monkeypatch.setattr(module, "chain_db_path", lambda: db_file)
