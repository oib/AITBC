"""Tests for scripts/ops/verify-genesis-root.py (C11).

The script's aitbc_chain imports are lazy (inside ``verify``), so this module
loads the script directly by path — same pattern as test_replay_chain.py.
The good-file fixture builds its claimed root/hash through the node's real
StateManager and compute_block_hash, so a PASS proves the tool agrees with
the production code paths rather than a reimplementation.
"""

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "verify-genesis-root.py"

spec = importlib.util.spec_from_file_location("verify_genesis_root", SCRIPT)
vgr = importlib.util.module_from_spec(spec)
sys.modules["verify_genesis_root"] = vgr
spec.loader.exec_module(vgr)

from aitbc_chain.consensus.block_hash import compute_block_hash
from aitbc_chain.state.merkle_patricia_trie import MerklePatriciaTrie, StateManager

CHAIN_ID = "ait-testchain"
TIMESTAMP = "2026-10-08T00:00:00+00:00"
PROPOSER = "genesis"

ADDR_A = "0x" + "aa" * 20
ADDR_B = "0x" + "bb" * 20

ALLOCS = [
    {"address": ADDR_A, "balance": 1_000_000, "nonce": 0},
    {"address": ADDR_B, "balance": 5_000, "nonce": 2},
]


def _root_of(allocs) -> str:
    sm = StateManager()
    for a in allocs:
        sm.update_account(a["address"], int(a["balance"]), int(a.get("nonce", 0)))
    return "0x" + sm.get_root().hex()


def _hash_of(root: str) -> str:
    return compute_block_hash(
        CHAIN_ID,
        0,
        "0x00",
        TIMESTAMP,
        [],
        PROPOSER,
        state_root=root,
        bridge_state_root="0x" + MerklePatriciaTrie().get_root().hex(),
    )


def _write(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "genesis.json"
    p.write_text(json.dumps(doc))
    return p


def _good_doc() -> dict:
    root = _root_of(ALLOCS)
    return {
        "chain_id": CHAIN_ID,
        "timestamp": TIMESTAMP,
        "state_root": root,
        "genesis_hash": _hash_of(root),
        "allocations": ALLOCS,
        "block": {
            "chain_id": CHAIN_ID,
            "height": 0,
            "hash": _hash_of(root),
            "parent_hash": "0x00",
            "proposer": PROPOSER,
            "timestamp": TIMESTAMP,
            "tx_count": 0,
            "state_root": root,
        },
    }


def test_good_file_passes(tmp_path):
    report = vgr.verify(_write(tmp_path, _good_doc()))
    assert report["verdict"] == "PASS", report["problems"]
    assert report["computed_root"] == report["claimed_root"]
    assert report["recomputed_hash"] == report["claimed_hash"]


def test_wrong_root_fails(tmp_path):
    doc = _good_doc()
    doc["state_root"] = "0x" + "00" * 32
    doc["block"]["state_root"] = doc["state_root"]
    report = vgr.verify(_write(tmp_path, doc))
    assert report["verdict"] == "FAIL"
    assert any("state_root mismatch" in p for p in report["problems"])


def test_wrong_hash_fails(tmp_path):
    doc = _good_doc()
    doc["genesis_hash"] = "0x" + "11" * 32
    doc["block"]["hash"] = doc["genesis_hash"]
    report = vgr.verify(_write(tmp_path, doc))
    assert report["verdict"] == "FAIL"
    assert any("block hash mismatch" in p for p in report["problems"])


def test_empty_allocations_fail(tmp_path):
    doc = _good_doc()
    doc["allocations"] = []
    # keep claimed root/hash of the non-empty set — file is now internally
    # inconsistent as well as empty
    report = vgr.verify(_write(tmp_path, doc))
    assert report["verdict"] == "FAIL"
    assert any("empty allocation set" in p for p in report["problems"])
    assert any("state_root mismatch" in p for p in report["problems"])


def test_duplicate_allocation_fails(tmp_path):
    doc = _good_doc()
    doc["allocations"] = ALLOCS + [{"address": ADDR_B, "balance": 1, "nonce": 0}]
    # root stays the same (the dup overwrites in the trie) but the dup must
    # still be reported — a stale trailing allocation is a data bug
    doc["state_root"] = _root_of(doc["allocations"])
    doc["genesis_hash"] = _hash_of(doc["state_root"])
    doc["block"]["state_root"] = doc["state_root"]
    doc["block"]["hash"] = doc["genesis_hash"]
    report = vgr.verify(_write(tmp_path, doc))
    assert report["verdict"] == "FAIL"
    assert any("duplicated allocation" in p for p in report["problems"])


def test_missing_file_fails_cleanly(tmp_path):
    report = vgr.verify(tmp_path / "nope.json")
    assert report["verdict"] == "FAIL"
    assert any("unreadable" in p for p in report["problems"])


def test_main_exit_codes(tmp_path, capsys):
    good = _write(tmp_path, _good_doc())
    assert vgr.main([str(good), "--quiet"]) == 0
    out = capsys.readouterr().out
    assert "verdict: PASS" in out
    bad_doc = _good_doc()
    bad_doc["allocations"] = []
    bad = _write(tmp_path, bad_doc)
    assert vgr.main([str(bad), "--quiet"]) == 1
    out = capsys.readouterr().out
    assert "verdict: FAIL" in out


def test_no_full_hashes_in_output(tmp_path, capsys):
    """The tool must never print a full 64-hex string."""
    doc = _good_doc()
    doc["state_root"] = "0x" + "00" * 32
    p = _write(tmp_path, doc)
    vgr.main([str(p)])
    out = capsys.readouterr().out
    import re

    assert not re.search(r"0x[0-9a-fA-F]{64}", out), out
