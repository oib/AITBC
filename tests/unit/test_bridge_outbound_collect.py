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


def _ledger(
    tmp_path: Path,
    releases: list[str] | None = None,
    sell_releases: list[str] | None = None,
    settlement_releases: list[str] | None = None,
) -> Path:
    db = tmp_path / "ledger.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE eth_deposits (id TEXT PRIMARY KEY, from_address TEXT)")
    con.execute("INSERT INTO eth_deposits VALUES ('d1', ?)", (DEPOSITOR,))
    if releases is not None:
        con.execute("CREATE TABLE eth_withdrawals (id TEXT PRIMARY KEY, eth_tx_hash TEXT)")
        con.executemany("INSERT INTO eth_withdrawals VALUES (?, ?)", [(f"w{i}", h) for i, h in enumerate(releases)])
    if sell_releases is not None:
        con.execute("CREATE TABLE bridge_sell_locks (id TEXT PRIMARY KEY, eth_tx_hash TEXT)")
        con.executemany("INSERT INTO bridge_sell_locks VALUES (?, ?)", [(f"s{i}", h) for i, h in enumerate(sell_releases)])
    if settlement_releases is not None:
        con.execute("CREATE TABLE exchange_settlements (id TEXT PRIMARY KEY, eth_tx_hash TEXT)")
        con.executemany(
            "INSERT INTO exchange_settlements VALUES (?, ?)", [(f"x{i}", h) for i, h in enumerate(settlement_releases)]
        )
    con.commit()
    con.close()
    return db


def _tx(to, value, gas_used=21000, gas_price="2000000000", status=1, block_height=11913000):
    return {
        "tx_hash": "0x" + "ab" * 20,
        "to": to,
        "value_wei": str(value),
        "gas_used": gas_used,
        "gas_price_wei": gas_price,
        "status": status,
        "block_height": block_height,
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


def test_release_hash_classifies_as_withdrawal(tmp_path):
    tx = _tx(STRANGER, 1113060053784850)
    ledger = _ledger(tmp_path, releases=[tx["tx_hash"]])
    terms = boc.classify([tx], boc._load_depositors(ledger), set(), boc._load_release_sources(ledger))
    assert terms["withdrawals_wei"] == 1113060053784850
    assert terms["unidentified_wei"] == 0
    assert terms["refunds_wei"] == 0


def test_release_hash_beats_unidentified_even_to_depositor(tmp_path):
    # A recorded release hash is stronger evidence than the recipient class.
    tx = _tx(DEPOSITOR, 700)
    ledger = _ledger(tmp_path, releases=[tx["tx_hash"]])
    terms = boc.classify([tx], boc._load_depositors(ledger), set(), boc._load_release_sources(ledger))
    assert terms["withdrawals_wei"] == 700 and terms["refunds_wei"] == 0


def test_ledger_without_withdrawals_table_tolerated(tmp_path):
    # Pre-B13 ledgers have no eth_withdrawals — falls back to unidentified.
    tx = _tx(STRANGER, 700)
    ledger = _ledger(tmp_path)  # no withdrawals table
    assert boc._load_release_sources(ledger) == {}
    terms = boc.classify([tx], boc._load_depositors(ledger), set(), boc._load_release_sources(ledger))
    assert terms["unidentified_wei"] == 700


def test_failed_release_counts_gas_only(tmp_path):
    tx = _tx(STRANGER, 500, status=0)
    ledger = _ledger(tmp_path, releases=[tx["tx_hash"]])
    terms = boc.classify([tx], boc._load_depositors(ledger), set(), boc._load_release_sources(ledger))
    assert terms["withdrawals_wei"] == 0
    assert terms["gas_wei"] == 21000 * 2_000_000_000


def test_main_emits_onchain_document(tmp_path, capsys):
    txs_path = tmp_path / "txs.json"
    txs_path.write_text(json.dumps([_tx(DEPOSITOR, 500)]))
    rc = boc.main(["--txs", str(txs_path), "--ledger", str(_ledger(tmp_path)), "--balance-wei", "1000000"])
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["wallet_balance_wei"] == "1000000"
    assert doc["outbound"]["refunds_wei"] == "500"
    assert doc["outbound"]["withdrawals_wei"] == "0"


def test_sell_lock_release_classifies_as_withdrawal_with_note(tmp_path):
    tx = _tx(STRANGER, 51000)
    ledger = _ledger(tmp_path, sell_releases=[tx["tx_hash"]])
    releases = boc._load_release_sources(ledger)
    terms = boc.classify([tx], boc._load_depositors(ledger), set(), releases)
    assert terms["withdrawals_wei"] == 51000 and terms["unidentified_wei"] == 0
    rows = boc.emit_rows([tx], boc._load_depositor_map(ledger), set(), releases)
    assert rows[0]["kind"] == "withdrawal"
    assert rows[0]["note"] == "bridge_sell_locks release"


def test_settlement_release_classifies_as_withdrawal_with_note(tmp_path):
    tx = _tx(STRANGER, 114930000000000)
    ledger = _ledger(tmp_path, settlement_releases=[tx["tx_hash"]])
    releases = boc._load_release_sources(ledger)
    terms = boc.classify([tx], boc._load_depositors(ledger), set(), releases)
    assert terms["withdrawals_wei"] == 114930000000000
    rows = boc.emit_rows([tx], boc._load_depositor_map(ledger), set(), releases)
    assert rows[0]["note"] == "exchange_settlements release"


def test_eth_withdrawals_release_carries_no_note(tmp_path):
    tx = _tx(STRANGER, 700)
    ledger = _ledger(tmp_path, releases=[tx["tx_hash"]])
    rows = boc.emit_rows([tx], boc._load_depositor_map(ledger), set(), boc._load_release_sources(ledger))
    assert rows[0]["kind"] == "withdrawal" and rows[0]["note"] is None


def test_release_join_normalizes_prefixes(tmp_path):
    """#668: bare web3-spelled txs must join 0x-prefixed release rows and
    vice versa — the earlier lower()-only join misclassified them."""
    h = "0xAbC" + "9" * 60
    ledger = _ledger(tmp_path, releases=[h])
    releases = boc._load_release_sources(ledger)
    assert boc._canon_tx_hash(h) in releases

    bare = h[2:].lower()
    txs = [{"tx_hash": bare, "to": STRANGER, "value_wei": 10, "block_height": 1}]
    terms = boc.classify(txs, depositors=set(), funding=set(), releases=releases)
    assert terms["withdrawals_wei"] == 10
    rows = boc.emit_rows(txs, depositor_map={}, funding=set(), releases=releases)
    assert rows[0]["kind"] == "withdrawal"
    assert rows[0]["tx_hash"] == boc._canon_tx_hash(h)  # emitted canonical, like record_outbound
