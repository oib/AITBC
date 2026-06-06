"""Blockchain context database schema."""

from __future__ import annotations

# Table name prefixes for blockchain context
BLOCKCHAIN_TABLE_PREFIX = "blockchain_"

# Blockchain context table names
BLOCKCHAIN_STATUS_TABLE = f"{BLOCKCHAIN_TABLE_PREFIX}status"
BLOCKCHAIN_TRANSACTION_TABLE = f"{BLOCKCHAIN_TABLE_PREFIX}transaction"
