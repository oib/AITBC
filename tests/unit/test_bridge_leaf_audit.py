"""Tests for scripts/ops/bridge-leaf-audit.py (V-4 recompute audit).

Fixtures are tiny chain.db files carrying just the columns the audit selects:
``transaction`` (chain_id, tx_hash, block_height, payload, envelope, type),
``cross_chain_transfer`` and ``block``. The cases mirror the three real-world
leaf shapes: transfer row present, row missing (0:unknown), and a GAP-47
block-scoped lock whose payload is empty so the envelope supplies the body.
"""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "bridge-leaf-audit.py"
CHAIN = "ait-test"


def _load():
    spec = importlib.util.spec_from_file_location("bridge_leaf_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bridge_leaf_audit"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool():
    return _load()


def _mk_db(path: Path, rows: list[tuple]) -> Path:
    """rows: (tx_hash, height, payload_dict, envelope_dict, transfer_or_None)
    transfer_or_None: (transfer_id, amount, target_chain, recipient) for the
    local row (recipient needed once the v2 leaf arms)."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT,
                            bridge_state_root TEXT);
        CREATE TABLE "transaction" (
            chain_id TEXT, tx_hash TEXT, block_height INTEGER,
            payload TEXT, envelope TEXT, type TEXT);
        CREATE TABLE cross_chain_transfer (
            transfer_id TEXT, source_chain TEXT, amount INTEGER,
            target_chain TEXT, recipient TEXT);
        """
    )
    for tx_hash, height, payload, envelope, transfer in rows:
        conn.execute(
            'INSERT INTO "transaction" VALUES (?, ?, ?, ?, ?, ?)',
            (CHAIN, tx_hash, height, json.dumps(payload), json.dumps(envelope) if envelope else None, "BRIDGE_LOCK"),
        )
        conn.execute(
            "INSERT INTO block (chain_id, height, hash, bridge_state_root) VALUES (?, ?, ?, ?)",
            (CHAIN, height, "h" + str(height), None),
        )
        if transfer is not None:
            conn.execute(
                "INSERT INTO cross_chain_transfer VALUES (?, ?, ?, ?, ?)",
                (transfer[0], CHAIN, transfer[1], transfer[2], transfer[3]),
            )
    conn.commit()
    conn.close()
    return path


def test_leaf_with_row_agrees(tool):
    cur, src = tool.current_leaf("txhash1", ("txhash1", 500, "ait-dest", "0xrecip"))
    assert src == "row" and cur == "lock:txhash1:500:ait-dest"
    der, dsrc = tool.derived_leaf(
        "txhash1",
        {"transfer_id": "txhash1", "amount": 500, "target_chain": "ait-dest"},
        {},
    )
    assert dsrc == "payload" and der == cur


def test_missing_row_leaf(tool):
    cur, src = tool.current_leaf("txhash2", None)
    assert src == "missing-row" and cur == "lock:txhash2:0:unknown"
    der, dsrc = tool.derived_leaf(
        "txhash2",
        {"transfer_id": "txhash2", "amount": 7, "target_chain": "ait-dest"},
        {},
    )
    # Derived is still available — this is the divergence V-4 removes.
    assert der == "lock:txhash2:7:ait-dest" and der != cur


def test_envelope_fallback_gap47(tool):
    """Empty payload (block-scoped lock) → envelope supplies the body."""
    der, src = tool.derived_leaf(
        "txhash3",
        {},
        {"transfer_id": "txhash3", "amount": 900, "target_chain": "ait-dest"},
    )
    assert src == "envelope" and der == "lock:txhash3:900:ait-dest"


def test_unreadable_lock(tool):
    der, src = tool.derived_leaf("txhash4", {}, {})
    assert der is None and src == "unreadable"


def test_v2_leaf_binds_recipient(tool, monkeypatch):
    """Post-arming leaves carry the recipient; missing recipient → underivable."""
    monkeypatch.setattr(tool, "_V2_HEIGHT", 50_000)
    cur, src = tool.current_leaf("txh", ("txh", 500, "ait-dest", "0xrecip"), 50_001)
    assert cur == "lock:txh:500:ait-dest:0xrecip" and src == "row"
    der, dsrc = tool.derived_leaf(
        "txh",
        {"transfer_id": "txh", "amount": 500, "target_chain": "ait-dest", "recipient": "0xrecip"},
        {},
        50_001,
    )
    assert der == cur and dsrc == "payload"
    # Below the arm height the same data keeps the 3-field leaf.
    cur1, _ = tool.current_leaf("txh", ("txh", 500, "ait-dest", "0xrecip"), 49_999)
    assert cur1 == "lock:txh:500:ait-dest"
    # Missing recipient at/above the arm height cannot be derived.
    der2, dsrc2 = tool.derived_leaf("txh", {"transfer_id": "txh", "amount": 5, "target_chain": "d"}, {}, 50_001)
    assert der2 is None and dsrc2 == "unreadable"


def test_v2_leaf_target_recipient_key(tool, monkeypatch):
    """Sealed envelopes carry the recipient as ``target_recipient`` (AUDIT-RECIP-1):
    a v2-height lock whose envelope has only that key still derives, source ``envelope``."""
    monkeypatch.setattr(tool, "_V2_HEIGHT", 50_000)
    der, src = tool.derived_leaf(
        "txh",
        {},
        {"transfer_id": "txh", "amount": 500, "target_chain": "ait-dest", "target_recipient": "0xrecip"},
        50_001,
    )
    assert der == "lock:txh:500:ait-dest:0xrecip" and src == "envelope"
    # Payload carrying only the alias also works.
    der2, src2 = tool.derived_leaf(
        "txh",
        {"transfer_id": "txh", "amount": 500, "target_chain": "ait-dest", "target_recipient": "0xrecip"},
        {},
        50_001,
    )
    assert der2 == "lock:txh:500:ait-dest:0xrecip" and src2 == "payload"
    # Neither key present at v2 height → still underivable.
    der3, src3 = tool.derived_leaf(
        "txh",
        {},
        {"transfer_id": "txh", "amount": 500, "target_chain": "ait-dest"},
        50_001,
    )
    assert der3 is None and src3 == "unreadable"
    # And the derivable v2 lock classifies derivable, not missing_data.
    assert tool.lock_class("envelope", 50_001, 30_000) == "derivable"
    # Pre-v2 the same alias-less body keeps the 3-field leaf unchanged.
    der4, _ = tool.derived_leaf(
        "txh",
        {},
        {"transfer_id": "txh", "amount": 500, "target_chain": "ait-dest"},
        49_999,
    )
    assert der4 == "lock:txh:500:ait-dest"


def test_audit_counts(tool, tmp_path):
    db = _mk_db(
        tmp_path / "a.db",
        [
            ("aa11", 1, {"transfer_id": "aa11", "amount": 5, "target_chain": "d"}, None, ("aa11", 5, "d", "0xrecip")),
            ("bb22", 1, {"transfer_id": "bb22", "amount": 6, "target_chain": "d"}, None, None),
            ("cc33", 2, {}, {"transfer_id": "cc33", "amount": 7, "target_chain": "d"}, ("cc33", 7, "d", "0xrecip")),
        ],
    )
    conn = tool.connect_ro(str(db))
    res = tool.audit(conn, use_trie=False)
    conn.close()
    assert res["locks_sealed"] == 3
    assert res["current_leaf"] == {"row": 2, "missing-row": 1}
    assert res["derived_leaf"] == {"payload": 2, "envelope": 1, "unreadable": 0}
    assert res["leaves"]["agree"] == 2
    assert res["leaves"]["differ"] == 1
    assert res["leaves"]["differ_only_missing_row"] == 1


def test_root_rebuild_matches_consensus_encoding(tool, tmp_path):
    """Rebuild the same root consensus produces and compare against a header
    value computed with the real MerklePatriciaTrie."""
    mpt = pytest.importorskip("aitbc_chain.state.merkle_patricia_trie")
    leaves = {"aa11": "lock:aa11:5:d", "bb22": "lock:bb22:6:d"}
    trie = mpt.MerklePatriciaTrie()
    for k, v in leaves.items():
        trie.put(k.encode(), v.encode())
    expected_root = "0x" + trie.get_root().hex()

    db = _mk_db(
        tmp_path / "a.db",
        [
            ("aa11", 1, {"transfer_id": "aa11", "amount": 5, "target_chain": "d"}, None, ("aa11", 5, "d", "0xrecip")),
            ("bb22", 1, {"transfer_id": "bb22", "amount": 6, "target_chain": "d"}, None, ("bb22", 6, "d", "0xrecip")),
        ],
    )
    conn = tool.connect_ro(str(db))
    res = tool.audit(conn)
    conn.close()
    assert res["trie_rebuilt"] is True
    assert res["blocks"][0]["derived_root"] == expected_root
    # Header absent (bridge_state_root NULL) → counted, not a mismatch.
    assert res["root_verdicts"]["header_absent"] == 1


def test_no_row_data_in_output(tool, tmp_path, capsys):
    db = _mk_db(
        tmp_path / "a.db",
        [("aa11", 1, {"transfer_id": "aa11", "amount": 5, "target_chain": "d"}, None, ("aa11", 5, "d", "0xrecip"))],
    )
    assert tool.main(["--db", str(db), "--no-trie"]) == 0
    out = capsys.readouterr().out
    assert "aa11" not in out  # even truncated refs only appear when breaking
    assert "sealed BRIDGE_LOCKs: 1" in out


def test_connection_is_query_only(tool, tmp_path):
    db = _mk_db(tmp_path / "a.db", [])
    conn = tool.connect_ro(str(db))
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO cross_chain_transfer VALUES ('x','y',1,'z','r')")
    conn.close()


def test_wal_contents_visible(tool, tmp_path):
    """Plain mode=ro must honor the WAL: a live node holds its newest commits
    in chain.db-wal and immutable=1 would skip them, so a lock sealed in an
    uncheckpointed page must still be audited."""
    db = tmp_path / "wal.db"
    writer = sqlite3.connect(db)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.executescript(
        """
        CREATE TABLE block (chain_id TEXT, height INTEGER, hash TEXT,
                            bridge_state_root TEXT);
        CREATE TABLE "transaction" (
            chain_id TEXT, tx_hash TEXT, block_height INTEGER,
            payload TEXT, envelope TEXT, type TEXT);
        CREATE TABLE cross_chain_transfer (
            transfer_id TEXT, source_chain TEXT, amount INTEGER,
            target_chain TEXT, recipient TEXT);
        """
    )
    writer.execute(
        'INSERT INTO "transaction" VALUES (?, ?, ?, ?, ?, ?)',
        (
            CHAIN,
            "wal1",
            9,
            json.dumps({"transfer_id": "wal1", "amount": 3, "target_chain": "ait-dest"}),
            None,
            "BRIDGE_LOCK",
        ),
    )
    writer.execute(
        "INSERT INTO block (chain_id, height, hash, bridge_state_root) VALUES (?, ?, ?, ?)",
        (CHAIN, 9, "h9", None),
    )
    writer.commit()
    try:
        assert (tmp_path / "wal.db-wal").exists(), "fixture must hold uncheckpointed WAL pages"
        conn = tool.connect_ro(str(db))
        res = tool.audit(conn, use_trie=False)
        conn.close()
        assert res["locks_sealed"] == 1  # the WAL row — invisible under immutable=1
    finally:
        writer.close()


# --- V-4 grandfathering boundary fixtures -------------------------------------


def test_lock_class_without_boundary(tool):
    assert tool.lock_class("payload", 100, None) == "derivable"
    assert tool.lock_class("envelope", 100, None) == "derivable"
    assert tool.lock_class("unreadable", 100, None) == "underivable"


def test_lock_class_boundary_split(tool):
    """Below the activation height an unreadable lock is grandfathered;
    at/above it the same lock is a missing_data defect the guard must block."""
    assert tool.lock_class("unreadable", 9999, 10000) == "grandfathered"
    assert tool.lock_class("unreadable", 10000, 10000) == "missing_data"
    assert tool.lock_class("unreadable", 10001, 10000) == "missing_data"
    assert tool.lock_class("payload", 50, 10000) == "derivable"


def test_audit_boundary_counts(tool, tmp_path):
    """End-to-end: one legacy empty-payload lock below the boundary is
    grandfathered; an identical lock above it counts as missing_data."""
    rows = [
        ("tx_legacy", 8259, {}, None, None),  # like the 4 live legacy locks
        ("tx_future", 30000, {}, None, None),  # same shape after the boundary
        ("tx_derivable", 31000, {"transfer_id": "t1", "amount": 5, "target_chain": "ait-dest"}, None, None),
    ]
    db = _mk_db(tmp_path / "b.db", rows)
    conn = tool.connect_ro(str(db))
    result = tool.audit(conn, use_trie=False, boundary=10000)
    conn.close()
    lc = result["lock_classes"]
    assert lc == {"derivable": 1, "grandfathered": 1, "missing_data": 1}
    # and the unit-level function pins which tx lands in which class
    assert tool.lock_class("unreadable", 8259, 10000) == "grandfathered"
    assert tool.lock_class("unreadable", 30000, 10000) == "missing_data"
    assert tool.lock_class("payload", 31000, 10000) == "derivable"


def test_cli_default_boundary_is_operator_choice(tool, tmp_path, capsys):
    """Operator chose boundary 30000 (2026-10-08): the CLI applies the V-4
    classification by default — a legacy unreadable lock below it is
    grandfathered without passing --boundary explicitly."""
    assert tool.GRANDFATHER_BOUNDARY == 30000
    db = _mk_db(tmp_path / "d.db", [("tx_legacy", 8259, {}, None, None)])
    assert tool.main(["--db", str(db), "--no-trie"]) == 0
    out = capsys.readouterr().out
    assert "boundary 30000" in out
    assert "grandfathered=1" in out
