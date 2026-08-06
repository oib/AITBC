#!/usr/bin/env python3
"""
Migration script for v0.5.10 hard fork - scale all on-chain values by 3600x

This script multiplies all balances, amounts, and fees by 3600 to convert from
raw AIT to compute-seconds (1 AIT = 3600 seconds).

Usage:
    python3 scripts/migration/scale_balances_3600x.py --chain-id CHAIN_ID --data-path PATH

Both flags are required and have no defaults: this rewrite is irreversible, so the target
chain must always be named explicitly. The run then asks for the chain id to be typed back
before it proceeds. Set CONFIRM_BALANCE_MIGRATION=yes to skip that prompt in automation.

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
import os
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path


def backup_file(file_path: Path) -> Path | None:
    """Create a backup of a file. Returns None when there was nothing to back up."""
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
        cursor.execute('UPDATE "transaction" SET value = value * 3600, fee = fee * 3600')
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


def _load_state_manager():
    """Import the blockchain node's StateManager.

    The migration must produce the same root the node will compute at startup, so it uses
    the node's own Merkle Patricia Trie rather than reimplementing one. Imported lazily and
    by path because this script runs standalone, outside the node's package.
    """
    import sys

    node_src = Path(__file__).resolve().parents[2] / "apps" / "blockchain-node" / "src"
    if not node_src.is_dir():
        raise RuntimeError(
            f"Cannot locate the blockchain node source at {node_src}. "
            "The genesis state root must be computed with the chain's own trie."
        )
    if str(node_src) not in sys.path:
        sys.path.insert(0, str(node_src))

    from aitbc_chain.state.merkle_patricia_trie import StateManager  # noqa: PLC0415

    return StateManager


def recalculate_state_root(db_path: Path, chain_id: str) -> str | None:
    """Recalculate the genesis state root from the scaled balances.

    Uses aitbc_chain.state.merkle_patricia_trie.StateManager -- the same implementation
    the node uses via state_root_utils.compute_state_root_full -- so the value written
    here is the value the node will compute when it validates genesis.

    This previously hashed a concatenated "address:balance:nonce;" string with sha256 and
    wrote that as the state root. The node computes an MPT root, so the two could never
    agree: after an irreversible x3600 balance rewrite, the chain would fail genesis
    validation. The script also printed the root and reported success, so the mismatch was
    invisible until a node was started.
    """
    try:
        state_manager_cls = _load_state_manager()
    except Exception as e:
        print(f"❌ Cannot load the chain's state-root implementation: {e}")
        print("   Refusing to write a state root the node will not accept.")
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        print("\n🔐 Recalculating state root (Merkle Patricia Trie)...")

        cursor.execute("SELECT address, balance, nonce FROM account WHERE chain_id=?", (chain_id,))
        accounts = cursor.fetchall()
        if not accounts:
            print("❌ No accounts found for chain; cannot recalculate state root.")
            return None

        state_manager = state_manager_cls()
        # Sorted for determinism. The trie is order-independent, but a stable order keeps
        # runs comparable when debugging a mismatch.
        for address, balance, nonce in sorted(accounts):
            state_manager.update_account(address, int(balance), int(nonce))

        # "0x"-prefixed to match compute_state_root_full; the node compares the stored
        # value against that string, so the prefix is part of the format.
        state_root: str = "0x" + state_manager.get_root().hex()
        print(f"  ✅ New state root: {state_root}")
        print(f"     ({len(accounts)} accounts, computed with the node's trie)")

        cursor.execute("UPDATE block SET state_root = ? WHERE height=0 AND chain_id=?", (state_root, chain_id))
        if cursor.rowcount == 0:
            print("❌ Genesis block not found; cannot update state root.")
            return None

        conn.commit()
        print("  ✅ Updated genesis block state_root in database")

        return state_root

    except sqlite3.Error as e:
        print(f"❌ Error recalculating state root: {e}")
        return None
    except Exception as e:
        print(f"❌ Error computing state root with the chain trie: {e}")
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
        cursor.execute('SELECT tx_hash, fee FROM "transaction" WHERE chain_id=? LIMIT 3', (chain_id,))
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


def confirm_migration(chain_id: str, data_path: Path) -> bool:
    """Require explicit confirmation before an irreversible balance rewrite.

    Multiplying every balance by 3600 cannot be undone except by restoring the backup this
    script takes moments earlier. It previously ran straight through with no prompt, on
    defaults that pointed at production.
    """
    if os.environ.get("CONFIRM_BALANCE_MIGRATION") == "yes":
        print("CONFIRM_BALANCE_MIGRATION=yes set; proceeding without an interactive prompt.")
        return True

    if not sys.stdin.isatty():
        print("❌ Refusing to run non-interactively without CONFIRM_BALANCE_MIGRATION=yes.")
        return False

    print("\n⚠️  This multiplies EVERY balance on this chain by 3600. It cannot be undone")
    print("   except by restoring the backup taken during this run.")
    print(f"   Chain:     {chain_id}")
    print(f"   Data path: {data_path}")
    answer = input("\n   Type the chain id to continue: ").strip()
    if answer != chain_id:
        print("❌ Confirmation did not match the chain id; aborting.")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Scale on-chain balances by 3600x for v0.5.10 hard fork")
    # No defaults. These pointed at the production chain and /var/lib/aitbc/data, so
    # running the script bare rewrote production balances. Both are now required.
    parser.add_argument("--chain-id", required=True, help="Chain ID (required; no default)")
    parser.add_argument("--data-path", required=True, help="Data directory path (required; no default)")
    args = parser.parse_args()

    chain_id = args.chain_id
    data_path = Path(args.data_path) / chain_id

    print(f"🚀 Starting v0.5.10 hard fork migration for chain: {chain_id}")
    print(f"📁 Data path: {data_path}")

    # Check data path exists
    if not data_path.exists():
        print(f"❌ Data path does not exist: {data_path}")
        return 1

    if not confirm_migration(chain_id, data_path):
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
        print("❌ Could not recalculate state root; migration aborted.")
        return 1

    # Update genesis.json with new state root
    if not update_genesis_json_state_root(genesis_path, state_root):
        print("❌ Could not update genesis.json; migration aborted.")
        return 1

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
