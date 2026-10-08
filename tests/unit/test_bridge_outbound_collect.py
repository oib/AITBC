"""Fixture tests for scripts/ops/bridge_outbound_collect.py (BR-6)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))
import bridge_outbound_collect as boc  # noqa: E402

DEPOSITOR = "0x1111111111111111111111111111111111111111"
FUNDING = "0x2222222222222222222222222222222222222222"
STRANGER = "0x3333333333333333333333333333333333333333"


def _ledger(tmp_path: Path) -> Path:
    db = tmp_path / "ledger.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE eth_deposits (id TEXT PRIMARY KEY, from_address TEXT)")
    con.execute("INSERT INTO eth_deposits VALUES ('d1', ?)", (DEPOSITOR,))
    con.commit()
    con.close()
    return db


def _tx(to, value, gas_used=21000, gas_price="2000000000", status=1):
    return {
        "tx_hash": "0x" + "ab" * 20,
        "to": to,
        "value_wei": str(value),
        "gas_used": gas_used,
        "gas_price_wei": gas_price,
        "status": status,
    }


def test_refund_to_depositor(tmp_path):
    txs = [_tx(DEPOSITOR, 500)]
    terms = boc.classify(txs, boc._load_depositors(_ledger(tmp_path)), set())
    assert terms["refunds_wei"] == 500
    assert terms["gas_wei"] == 21000 * 2_000_000_000
    assert terms["unidentified_wei"] == 0


def test_funding_source_return_counts_as_refund(tmp_path):
    txs = [_tx(FUNDING, 900, gas_used=None, gas_price=None)]
    terms = boc.classify(txs, boc._load_depositors(_ledger(tmp_path)), {FUNDING.lower()})
    assert terms["refunds_wei"] == 900 and terms["gas_wei"] == 0


def test_unknown_recipient_is_unidentified(tmp_path):
    terms = boc.classify([_tx(STRANGER, 700)], boc._load_depositors(_ledger(tmp_path)), set())
    assert terms["unidentified_wei"] == 700 and terms["refunds_wei"] == 0


def test_failed_tx_counts_gas_only(tmp_path):
    terms = boc.classify([_tx(DEPOSITOR, 500, status=0)], boc._load_depositors(_ledger(tmp_path)), set())
    assert terms["refunds_wei"] == 0
    assert terms["gas_wei"] == 21000 * 2_000_000_000


def test_case_insensitive_matching(tmp_path):
    terms = boc.classify([_tx(DEPOSITOR.upper(), 500)], {DEPOSITOR}, set())
    assert terms["refunds_wei"] == 500


def test_malformed_tx_rejected():
    with pytest.raises(SystemExit):
        boc.classify([{"to": DEPOSITOR}], set(), set())


def test_main_emits_onchain_document(tmp_path, capsys):
    txs_path = tmp_path / "txs.json"
    txs_path.write_text(json.dumps([_tx(DEPOSITOR, 500)]))
    rc = boc.main(["--txs", str(txs_path), "--ledger", str(_ledger(tmp_path)), "--balance-wei", "1000000"])
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["wallet_balance_wei"] == "1000000"
    assert doc["outbound"]["refunds_wei"] == "500"
    assert doc["outbound"]["withdrawals_wei"] == "0"
