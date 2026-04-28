#!/usr/bin/env python3
"""
Genesis Block Initialization Script

This script creates genesis blocks and initializes accounts for AITBC chains.
It can be used to set up new chains or re-initialize existing ones.

Usage:
    python scripts/utils/genesis-init.py --chain-id ait-testnet --proposer <address> --balance <amount>
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


def compute_genesis_hash(height: int, parent_hash: str, timestamp: datetime) -> str:
    """Compute genesis block hash (simplified - in production use proper crypto)"""
    # For now, use a deterministic hash based on the genesis data
    data = f"{height}:{parent_hash}:{timestamp.isoformat()}:genesis"
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()


def create_genesis_json(
    chain_id: str,
    proposer: str,
    balance: int,
    output_path: Optional[Path] = None,
    chain_type: str = "testnet"
) -> Path:
    """Create genesis.json file for a chain"""
    
    timestamp = datetime(2025, 1, 1, 0, 0, 0)
    genesis_hash = compute_genesis_hash(0, "0x00", timestamp)
    
    genesis_data = {
        "chain_id": chain_id,
        "block": {
            "height": 0,
            "hash": genesis_hash,
            "parent_hash": "0x00",
            "proposer": proposer,
            "timestamp": timestamp.isoformat(),
            "tx_count": 0,
            "chain_id": chain_id,
            "state_root": "0x00",
            "metadata": {
                "chain_type": chain_type,
                "purpose": "testing" if chain_type == "testnet" else "production",
                "consensus_algorithm": "poa"
            }
        },
        "allocations": [
            {
                "address": proposer,
                "balance": balance,
                "nonce": 0
            }
        ]
    }
    
    if output_path is None:
        output_path = Path(f"/var/lib/aitbc/data/{chain_id}/genesis.json")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(genesis_data, f, indent=2)
    
    print(f"Created genesis.json at {output_path}")
    return output_path


def initialize_database(
    chain_id: str,
    proposer: str,
    balance: int,
    db_path: Optional[Path] = None
) -> None:
    """Initialize database with genesis block and account"""
    
    if db_path is None:
        db_path = Path(f"/var/lib/aitbc/data/{chain_id}/chain.db")
    
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables (simplified schema - matches SQLModel models)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS block (
            id INTEGER NOT NULL,
            chain_id VARCHAR NOT NULL,
            height INTEGER NOT NULL,
            hash VARCHAR NOT NULL,
            parent_hash VARCHAR NOT NULL,
            proposer VARCHAR NOT NULL,
            timestamp DATETIME NOT NULL,
            tx_count INTEGER NOT NULL,
            state_root VARCHAR,
            block_metadata VARCHAR,
            PRIMARY KEY (id),
            CONSTRAINT uix_block_chain_height UNIQUE (chain_id, height)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account (
            chain_id VARCHAR NOT NULL,
            address VARCHAR NOT NULL,
            balance INTEGER NOT NULL,
            nonce INTEGER NOT NULL,
            updated_at DATETIME NOT NULL,
            PRIMARY KEY (chain_id, address)
        )
    """)
    
    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_block_chain_id ON block (chain_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS ix_block_height ON block (height)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_block_hash ON block (hash)")
    
    # Check if genesis block already exists
    cursor.execute(
        "SELECT hash FROM block WHERE chain_id=? AND height=0",
        (chain_id,)
    )
    existing = cursor.fetchone()
    
    if existing:
        print(f"Genesis block already exists for chain {chain_id}")
        conn.close()
        return
    
    # Insert genesis block
    timestamp = datetime(2025, 1, 1, 0, 0, 0)
    genesis_hash = compute_genesis_hash(0, "0x00", timestamp)
    
    cursor.execute(
        """
        INSERT INTO block (chain_id, height, hash, parent_hash, proposer, timestamp, tx_count, state_root)
        VALUES (?, 0, ?, ?, ?, ?, 0, ?)
        """,
        (chain_id, genesis_hash, "0x00", proposer, timestamp.isoformat(), "0x00")
    )
    
    # Insert account with initial balance
    cursor.execute(
        """
        INSERT INTO account (chain_id, address, balance, nonce, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (chain_id, proposer, balance, 0, timestamp.isoformat())
    )
    
    conn.commit()
    conn.close()
    
    print(f"Initialized database for chain {chain_id}")
    print(f"Genesis block hash: {genesis_hash}")
    print(f"Account {proposer} balance: {balance}")


def main():
    parser = argparse.ArgumentParser(description="Initialize genesis block for AITBC chain")
    parser.add_argument("--chain-id", required=True, help="Chain ID (e.g., ait-testnet)")
    parser.add_argument("--proposer", required=True, help="Proposer address for genesis block")
    parser.add_argument("--balance", type=int, default=1000000000, help="Initial balance (default: 1,000,000,000)")
    parser.add_argument("--chain-type", default="testnet", choices=["mainnet", "testnet"], help="Chain type")
    parser.add_argument("--db-path", help="Custom database path")
    parser.add_argument("--genesis-path", help="Custom genesis.json path")
    parser.add_argument("--skip-genesis", action="store_true", help="Skip creating genesis.json")
    parser.add_argument("--skip-db", action="store_true", help="Skip database initialization")
    
    args = parser.parse_args()
    
    if not args.skip_genesis:
        genesis_path = Path(args.genesis_path) if args.genesis_path else None
        create_genesis_json(
            chain_id=args.chain_id,
            proposer=args.proposer,
            balance=args.balance,
            output_path=genesis_path,
            chain_type=args.chain_type
        )
    
    if not args.skip_db:
        db_path = Path(args.db_path) if args.db_path else None
        initialize_database(
            chain_id=args.chain_id,
            proposer=args.proposer,
            balance=args.balance,
            db_path=db_path
        )
    
    print(f"\nGenesis initialization complete for chain {args.chain_id}")


if __name__ == "__main__":
    main()
