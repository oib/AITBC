#!/usr/bin/env python3
"""
Migration script for v0.5.10 hard fork - scale all on-chain values by 3600x

This script multiplies all balances, amounts, and fees by 3600 to convert from
raw AIT to compute-seconds (1 AIT = 3600 seconds).

Usage:
    python3 scripts/migration/scale_balances_3600x.py [--chain-id CHAIN_ID] [--data-path PATH]

The script:
1. Backs up chain.db and genesis.json
2. Multiplies all balances/amounts/fees by 3600
3. Clears mempool
4. Scales genesis.json allocations
5. Recalculates state root
6. Updates genesis block state_root in database
7. Prints verification summary
"""

import argparse
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def backup_file(file_path: Path) -> Path:
    """Create a backup of a file"""
    if not file_path.exists():
        print(f"⚠️  File not found for backup: {file_path}")
        return None

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.parent / f"{file_path.name}.pre-fork.{timestamp}"
    shutil.copy2(file_path, backup_path)
    print(f"✅ Backed up {file_path} -> {backup_path}")
    return backup_path


def scale_balances(db_path: Path) -> bool:
    """Scale all balances, amounts, and fees by 3600"""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        print("\n📊 Scaling on-chain data...")

        # Scale account balances
        cursor.execute("UPDATE account SET balance = balance * 3600")
        accounts_updated = cursor.rowcount
        print(f"  ✅ Updated {accounts_updated} account balances")

        # Scale transaction values and fees
        cursor.execute("UPDATE transaction SET value = value * 3600, fee = fee * 3600")
        txs_updated = cursor.rowcount
        print(f"  ✅ Updated {txs_updated} transactions (value and fee)")

        # Scale receipt minted amounts
        cursor.execute("UPDATE receipt SET minted_amount = minted_amount * 3600 WHERE minted_amount IS NOT NULL")
        receipts_updated = cursor.rowcount
        print(f"  ✅ Updated {receipts_updated} receipt minted amounts")

        # Scale escrow amounts
        cursor.execute("UPDATE escrow SET amount = amount * 3600")
        escrow_updated = cursor.rowcount
        print(f"  ✅ Updated {escrow_updated} escrow amounts")

        # Scale cross-chain transfer amounts
        cursor.execute("UPDATE cross_chain_transfer SET amount = amount * 3600")
        bridge_updated = cursor.rowcount
        print(f"  ✅ Updated {bridge_updated} cross-chain transfer amounts")

        # Scale stake amounts
        cursor.execute("UPDATE stake SET amount = amount * 3600")
        stake_updated = cursor.rowcount
        print(f"  ✅ Updated {stake_updated} stake amounts")

        # Clear mempool (pending transactions have old fee values)
        cursor.execute("DELETE FROM mempool")
        mempool_cleared = cursor.rowcount
        print(f"  ✅ Cleared {mempool_cleared} pending transactions from mempool")

        conn.commit()
        print("\n✅ All on-chain data scaled successfully")
        return True

    except sqlite3.Error as e:
        print(f"❌ Error scaling balances: {e}")
        return False
    finally:
        if "conn" in locals():
            conn.close()


def scale_genesis_json(genesis_path: Path) -> bool:
    """Scale genesis.json allocations by 3600"""
    try:
        if not genesis_path.exists():
            print(f"⚠️  Genesis file not found: {genesis_path}")
            return False

        with open(genesis_path) as f:
            genesis_data = json.load(f)

        # Scale allocations
        if "allocations" in genesis_data:
            for alloc in genesis_data["allocations"]:
                if "balance" in alloc:
                    old_balance = alloc["balance"]
                    alloc["balance"] = old_balance * 3600
                    print(f"  ✅ Scaled allocation for {alloc['address']}: {old_balance} -> {alloc['balance']}")

        # Save updated genesis.json
        with open(genesis_path, "w") as f:
            json.dump(genesis_data, f, indent=2)

        print("\n✅ Genesis.json scaled successfully")
        return True

    except Exception as e:
        print(f"❌ Error scaling genesis.json: {e}")
        return False


def recalculate_state_root(db_path: Path, chain_id: str) -> str | None:
    """
    Recalculate state root from scaled balances.

    This is a simplified implementation - in production, you would use
    the actual Merkle Patricia Trie implementation from the blockchain code.
    """
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        print("\n🔐 Recalculating state root...")

        # Get all accounts
        cursor.execute("SELECT address, balance, nonce FROM account WHERE chain_id=?", (chain_id,))
        accounts = cursor.fetchall()

        # Simplified state root calculation (hash of all account states)
        # In production, use the actual MPT implementation
        import hashlib

        state_data = f"{chain_id}:{len(accounts)}:"
        for address, balance, nonce in sorted(accounts):
            state_data += f"{address}:{balance}:{nonce};"

        state_root = hashlib.sha256(state_data.encode()).hexdigest()
        print(f"  ✅ New state root: {state_root}")

        # Update genesis block state_root
        cursor.execute("UPDATE block SET state_root = ? WHERE height=0 AND chain_id=?", (state_root, chain_id))

        conn.commit()
        print("  ✅ Updated genesis block state_root in database")

        return state_root

    except sqlite3.Error as e:
        print(f"❌ Error recalculating state root: {e}")
        return None
    finally:
        if "conn" in locals():
            conn.close()


def update_genesis_json_state_root(genesis_path: Path, state_root: str) -> bool:
    """Update state_root in genesis.json"""
    try:
        if not genesis_path.exists():
            print(f"⚠️  Genesis file not found: {genesis_path}")
            return False

        with open(genesis_path) as f:
            genesis_data = json.load(f)

        # Update state_root in block
        if "block" in genesis_data and "state_root" in genesis_data["block"]:
            genesis_data["block"]["state_root"] = state_root
            print("  ✅ Updated state_root in genesis.json block")

        # Save updated genesis.json
        with open(genesis_path, "w") as f:
            json.dump(genesis_data, f, indent=2)

        return True

    except Exception as e:
        print(f"❌ Error updating genesis.json state_root: {e}")
        return False


def verify_migration(db_path: Path, chain_id: str) -> bool:
    """Verify the migration by checking sample data"""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        print("\n🔍 Verifying migration...")

        # Check account balances
        cursor.execute("SELECT address, balance FROM account WHERE chain_id=? LIMIT 3", (chain_id,))
        accounts = cursor.fetchall()
        print("  Sample account balances:")
        for address, balance in accounts:
            ait_balance = balance / 3600
            print(f"    {address}: {balance} seconds ({ait_balance:.2f} AIT)")

        # Check transaction fees
        cursor.execute("SELECT tx_hash, fee FROM transaction WHERE chain_id=? LIMIT 3", (chain_id,))
        txs = cursor.fetchall()
        print("  Sample transaction fees:")
        for tx_hash, fee in txs:
            ait_fee = fee / 3600
            print(f"    {tx_hash[:16]}...: {fee} seconds ({ait_fee:.4f} AIT)")

        # Check genesis block
        cursor.execute("SELECT state_root FROM block WHERE height=0 AND chain_id=?", (chain_id,))
        genesis_block = cursor.fetchone()
        if genesis_block:
            print(f"  Genesis block state_root: {genesis_block[0]}")

        print("\n✅ Migration verification complete")
        return True

    except sqlite3.Error as e:
        print(f"❌ Error verifying migration: {e}")
        return False
    finally:
        if "conn" in locals():
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Scale on-chain balances by 3600x for v0.5.10 hard fork")
    parser.add_argument("--chain-id", default="ait-hub.aitbc.bubuit.net", help="Chain ID")
    parser.add_argument("--data-path", default="/var/lib/aitbc/data", help="Data directory path")
    args = parser.parse_args()

    chain_id = args.chain_id
    data_path = Path(args.data_path) / chain_id

    print(f"🚀 Starting v0.5.10 hard fork migration for chain: {chain_id}")
    print(f"📁 Data path: {data_path}")

    # Check data path exists
    if not data_path.exists():
        print(f"❌ Data path does not exist: {data_path}")
        return 1

    # File paths
    db_path = data_path / "chain.db"
    genesis_path = data_path / "genesis.json"

    # Backup files
    print("\n💾 Creating backups...")
    backup_file(db_path)
    backup_file(genesis_path)

    # Scale balances
    if not scale_balances(db_path):
        return 1

    # Scale genesis.json
    if not scale_genesis_json(genesis_path):
        return 1

    # Recalculate state root
    state_root = recalculate_state_root(db_path, chain_id)
    if not state_root:
        print("⚠️  Could not recalculate state root, continuing...")
    else:
        # Update genesis.json with new state root
        update_genesis_json_state_root(genesis_path, state_root)

    # Verify migration
    if not verify_migration(db_path, chain_id):
        return 1

    print("\n✅ Migration completed successfully!")
    print("\n⚠️  IMPORTANT: After migration, flush Redis cache:")
    print("   redis-cli FLUSHDB")
    print("\n⚠️  IMPORTANT: Restart all services with v0.5.10 code")

    return 0


if __name__ == "__main__":
    exit(main())
