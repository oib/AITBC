"""Pins for scripts/utils/reset_chain_0x.py (RESET-CHAIN-0X-GENESIS-HASH-1, #932).

The script resolves its chain id and data dir through ``aitbc_chain.config``'s
import-time settings singleton, so — like the CLI's ``genesis reset`` — the
test runs it in a subprocess with the scratch env already exported. The
genesis claims are then recomputed the way ``poa._ensure_genesis_block`` /
``_verify_genesis_claims`` does: state root via ``StateManager.update_account``
over the allocations and the block hash via ``compute_block_hash`` over the
document's fields.
"""

import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


from aitbc_chain.consensus.block_hash import compute_block_hash
from aitbc_chain.genesis_builder import empty_bridge_root
from aitbc_chain.state.merkle_patricia_trie import StateManager

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "utils" / "reset_chain_0x.py"

CHAIN_ID = "tst-reset932"
GENESIS_ADDRESS = "0x" + "11" * 20


def _run_reset(tmp_path: Path) -> tuple[Path, Path, dict]:
    """Run the script in a scratch root; return (scratch_root, chain_db, genesis_doc)."""
    root = tmp_path / "scratch-root"
    etc = root / "etc"
    etc.mkdir(parents=True)
    (etc / "node.env").write_text(f"GENESIS_ADDRESS={GENESIS_ADDRESS}\n")
    (root / "wallets").mkdir()
    db = root / "data" / CHAIN_ID / "chain.db"

    env = dict(os.environ)
    env.update(
        {
            "AITBC_RESET_SCRATCH": str(root),
            "AITBC_DATA_DIR": str(root),
            "CHAIN_ID": CHAIN_ID,
            "DB_PATH": str(db),
            "AITBC_ETC_DIR": str(etc),
            "AITBC_WALLETS_DIR": str(root / "wallets"),
            "AITBC_SERVICE_KEYS_FILE": str(root / "keystore" / "service_accounts.json"),
            "GENESIS_YAML_OUT": str(root / "genesis_prod.yaml"),
        }
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"reset_chain_0x failed:\n{proc.stdout}\n{proc.stderr}"

    genesis_json = db.parent / "genesis.json"
    return root, db, json.loads(genesis_json.read_text())


def _loader_recompute(doc: dict) -> tuple[str, str]:
    """The two claims _verify_genesis_claims recomputes from the file's fields."""
    sm = StateManager()
    for alloc in doc["allocations"]:
        sm.update_account(str(alloc["address"]), int(alloc["balance"]), int(alloc.get("nonce", 0)))
    root = "0x" + sm.get_root().hex()
    block_hash = compute_block_hash(
        doc["chain_id"],
        0,
        "0x00",
        datetime.fromisoformat(doc["timestamp"]),
        [],
        "genesis",
        state_root=doc["state_root"],
        bridge_state_root=empty_bridge_root(),
    )
    return root, block_hash


def test_genesis_json_passes_loader_claims(tmp_path):
    _root, _db, doc = _run_reset(tmp_path)

    assert doc["chain_id"] == CHAIN_ID
    assert doc["timestamp"] == "2025-01-01T00:00:00+00:00"
    assert doc["parameters"] == {}
    assert doc["allocations"], "expected genesis + service-account allocations"

    computed_root, computed_hash = _loader_recompute(doc)
    assert computed_root.lower() == doc["state_root"].lower()
    assert computed_hash.lower() == doc["genesis_hash"].lower()


def test_db_block0_equals_loader_construction(tmp_path):
    _root, db, doc = _run_reset(tmp_path)

    row = (
        sqlite3.connect(db)
        .execute(
            "SELECT height, hash, parent_hash, proposer, tx_count, state_root, bridge_state_root, block_metadata "
            "FROM block WHERE chain_id=? AND height=0",
            (CHAIN_ID,),
        )
        .fetchone()
    )
    assert row is not None
    height, hash_, parent_hash, proposer, tx_count, state_root, bridge_root, metadata = row
    assert height == 0
    assert hash_ == doc["genesis_hash"]
    assert parent_hash == "0x00"
    assert proposer == "genesis"
    assert tx_count == 0
    assert state_root == doc["state_root"]
    assert bridge_root == empty_bridge_root()
    assert json.loads(metadata) == {"allocations": doc["allocations"]}

    # Every allocation is seeded with its document balance/nonce. init_db may
    # add its own zero-balance system rows — the loader's
    # _create_accounts_from_allocations adds the same set on top of them.
    account_rows = {
        (a, b, n)
        for a, b, n in sqlite3.connect(db)
        .execute("SELECT address, balance, nonce FROM account WHERE chain_id=?", (CHAIN_ID,))
        .fetchall()
    }
    expected = {(alloc["address"], int(alloc["balance"]), int(alloc.get("nonce", 0))) for alloc in doc["allocations"]}
    assert expected <= account_rows
