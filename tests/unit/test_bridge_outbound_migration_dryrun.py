"""Fixture tests for scripts/ops/bridge_outbound_migration_dryrun.py (BR-7)."""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import bridge_outbound_migration_dryrun as mod  # noqa: E402

DEPOSITOR = "0x1111111111111111111111111111111111111111"
DEPOSITOR_B = "0x3333333333333333333333333333333333333333"
FUNDING = "0x2222222222222222222222222222222222222222"
STRANGER = "0x4444444444444444444444444444444444444444"

GAS_WEI = 21000 * 2_000_000_000


def _deposits():
    return [
        {"id": "d1", "tx_hash": "0xdep1", "from_address": DEPOSITOR, "amount_eth": "1.0", "status": "completed"},
        {"id": "d2", "tx_hash": "0xdep2", "from_address": DEPOSITOR_B, "amount_eth": "0.5", "status": "completed"},
    ]


def _tx(tx_hash, to, value_wei, gas_used=21000, gas_price="2000000000", block=100):
    tx = {
        "tx_hash": tx_hash,
        "to": to,
        "value_wei": str(value_wei),
        "status": 1,
        "block_height": block,
    }
    if gas_used is not None:
        tx["gas_used"] = gas_used
    if gas_price is not None:
        tx["gas_price_wei"] = gas_price
    return tx


def test_demo_run_ok_and_scratch_cleaned(capsys):
    rc = mod.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "VERDICT: BALANCED" in out
    assert "DRY-RUN VERDICT: OK" in out
    m = re.search(r"^scratch:\s+(\S+)", out, re.M)
    assert m, out
    assert not Path(m.group(1)).exists()


def test_build_db_applies_b13_ddl_and_classifies(tmp_path):
    db = tmp_path / "ledger.db"
    txs = [
        _tx("0xout1", DEPOSITOR, 25 * 10**16),
        _tx("0xout2", FUNDING, 125 * 10**15, block=101),
        _tx("0xout3", STRANGER, 5 * 10**16, block=102),
    ]
    counts = mod.build_db(db, _deposits(), txs, {FUNDING.lower()})
    assert counts == {"refund": 1, "withdrawal": 1, "unidentified": 1}

    con = sqlite3.connect(db)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(bridge_outbound)")}
        assert mod.BRIDGE_OUTBOUND_COLUMNS <= cols
        rows = {r[0]: r for r in con.execute("SELECT tx_hash, kind, matched_deposit_tx FROM bridge_outbound")}
    finally:
        con.close()
    assert rows["0xout1"][1:] == ("refund", "0xdep1")
    assert rows["0xout2"][1:] == ("withdrawal", None)
    assert rows["0xout3"][1:] == ("unidentified", None)


def test_insert_or_ignore_dedupes_tx_hash(tmp_path):
    db = tmp_path / "ledger.db"
    tx = _tx("0xout1", DEPOSITOR, 25 * 10**16)
    # Same tx_hash twice in one pass, then a second pass with no new
    # deposits (eth_deposits uses plain INSERT and would UNIQUE-fail).
    mod.build_db(db, _deposits(), [tx, dict(tx)], {FUNDING.lower()})
    mod.build_db(db, [], [tx], {FUNDING.lower()})
    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT tx_hash, kind FROM bridge_outbound").fetchall()
    finally:
        con.close()
    assert rows == [("0xout1", "refund")]


def test_ledger_terms_wei_sums_and_ungassed(tmp_path):
    db = tmp_path / "ledger.db"
    txs = [
        _tx("0xout1", DEPOSITOR, 25 * 10**16),
        _tx("0xout2", FUNDING, 125 * 10**15, block=101),
        _tx("0xout3", STRANGER, 5 * 10**16, gas_used=None, gas_price=None, block=102),
    ]
    mod.build_db(db, _deposits(), txs, {FUNDING.lower()})
    terms = mod.ledger_terms(db)
    assert terms["refunds_wei"] == 25 * 10**16
    assert terms["withdrawals_wei"] == 125 * 10**15
    assert terms["unidentified_wei"] == 5 * 10**16
    assert terms["gas_wei"] == 2 * GAS_WEI
    assert terms["ungassed_rows"] == 1


def test_unidentified_outbound_still_balanced_but_flags(tmp_path, capsys):
    txs = [
        _tx("0xout1", DEPOSITOR, 25 * 10**16),
        _tx("0xout9", STRANGER, 5 * 10**16, block=109),
    ]
    txs_path = tmp_path / "txs.json"
    txs_path.write_text(json.dumps(txs), encoding="utf-8")
    rc = mod.main(["--txs", str(txs_path)])
    out = capsys.readouterr().out
    # Balance is derived from the same tx list, so the books still close…
    assert "VERDICT: BALANCED" in out
    # …but an unidentified leg must fail the dry-run gate.
    assert "DRY-RUN VERDICT: ATTENTION NEEDED" in out
    assert rc == 1


def test_scratch_dir_guard_refuses_var_lib():
    with pytest.raises(SystemExit, match="refusing scratch dir"):
        mod.main(["--scratch-dir", "/var/lib/br7-dryrun-refused"])
