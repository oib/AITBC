"""ETH-8 phase 3 ledger coverage (commit C1) — the exchange_settlements
table in bridge_deposits.db and its only-write-path helper.

Throwaway DBs only (DB_PATH patched to tmp_path); no live ledger, no keys.
"""

import sqlite3
from decimal import Decimal
from unittest.mock import patch

import pytest

from wallet_app.bridge import bridge_db


@pytest.fixture
def fresh_ledger(tmp_path):
    """Point bridge_db at a throwaway ledger and init it."""
    db_path = str(tmp_path / "bridge.db")
    with patch("wallet_app.bridge.bridge_db.DB_PATH", db_path):
        bridge_db.init_db()
        yield db_path


def _insert_trade(**over):
    args = {
        "kind": "trade",
        "ref_id": 1,
        "buy_order_id": 10,
        "sell_order_id": 20,
        "buyer_address": "0xbuyer",
        "seller_address": "0xseller",
        "seller_eth_address": "0xCf1719140054AB3fD52ce8aa3128dec9317426E3",
        "amount_ait": Decimal("5"),
        "eth_amount": Decimal("0.0005"),
        "fee_ait": Decimal("0"),
    }
    args.update(over)
    return bridge_db.insert_exchange_settlement(args.pop("kind"), args.pop("ref_id"), **args)


def test_table_created_idempotently(fresh_ledger):
    bridge_db.init_db()
    bridge_db.init_db()
    conn = sqlite3.connect(fresh_ledger)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(exchange_settlements)")}
    conn.close()
    assert {
        "kind",
        "ref_id",
        "status",
        "release_nonce",
        "escrow_out_nonce",
        "escrow_out_tx",
        "settle_ait_tx_hash",
        "settle_fee_tx_hash",
    } <= cols


def test_insert_and_get_roundtrip(fresh_ledger):
    sid = _insert_trade()
    assert sid and sid.startswith("exs_")
    row = bridge_db.get_exchange_settlement("trade", 1)
    assert row["id"] == sid
    assert row["status"] == "locked"
    assert row["buy_order_id"] == 10
    assert row["amount_ait"] == Decimal("5")


def test_unique_kind_ref_id_blocks_second_row(fresh_ledger):
    assert _insert_trade() is not None
    assert _insert_trade() is None  # same (trade, 1) — deduped, no exception
    # A different kind on the same ref_id is a distinct settlement.
    assert _insert_trade(kind="order_refund") is not None


def test_kind_check_rejects_unknown(fresh_ledger):
    with pytest.raises(ValueError, match="unknown settlement kind"):
        _insert_trade(kind="bogus")
    # And nothing was silently parked by OR IGNORE.
    assert bridge_db.get_exchange_settlement("trade", 1) is None


def test_open_settlements_excludes_terminal(fresh_ledger):
    _insert_trade(ref_id=1)
    _insert_trade(ref_id=2)
    sid = _insert_trade(ref_id=3)
    bridge_db.update_exchange_settlement(sid, "settled")
    open_ids = {r["ref_id"] for r in bridge_db.get_open_exchange_settlements()}
    assert open_ids == {1, 2}


def test_update_stamps_lifecycle_timestamps(fresh_ledger):
    sid = _insert_trade()
    bridge_db.update_exchange_settlement(sid, "releasing", eth_tx_hash="0xeth", release_nonce=4)
    row = bridge_db.get_exchange_settlement("trade", 1)
    assert row["status"] == "releasing" and row["released_at"] and row["eth_tx_hash"] == "0xeth"
    bridge_db.update_exchange_settlement(sid, "settled", settle_ait_tx_hash="0xait")
    row = bridge_db.get_exchange_settlement("trade", 1)
    assert row["settled_at"] and row["settle_ait_tx_hash"] == "0xait"


def test_null_args_never_blank_recorded_fields(fresh_ledger):
    sid = _insert_trade()
    bridge_db.update_exchange_settlement(sid, "releasing", eth_tx_hash="0xeth", release_nonce=4)
    bridge_db.update_exchange_settlement(sid, "released")  # no hash args
    row = bridge_db.get_exchange_settlement("trade", 1)
    assert row["eth_tx_hash"] == "0xeth" and row["release_nonce"] == 4


def test_update_unknown_id_returns_false(fresh_ledger):
    assert bridge_db.update_exchange_settlement("exs_missing", "settled") is False


def test_inflight_sweep_picks_only_sweep_statuses(fresh_ledger):
    _insert_trade(ref_id=1)
    assert bridge_db.get_exchange_inflight_sweep() is None
    sid = _insert_trade(ref_id=2)
    bridge_db.update_exchange_settlement(sid, "settling", escrow_out_nonce=3, escrow_out_tx="{}")
    found = bridge_db.get_exchange_inflight_sweep()
    assert found is not None and found["id"] == sid and found["escrow_out_nonce"] == 3


def test_pending_reserve_sums_only_reserve_statuses(fresh_ledger):
    _insert_trade(ref_id=1, eth_amount=Decimal("0.001"))  # locked -> reserves
    sid2 = _insert_trade(ref_id=2, eth_amount=Decimal("0.002"))
    sid3 = _insert_trade(ref_id=3, eth_amount=Decimal("0.004"))
    sid4 = _insert_trade(ref_id=4, eth_amount=Decimal("0.008"))
    bridge_db.update_exchange_settlement(sid2, "releasing", eth_tx_hash="0xa", release_nonce=1)
    bridge_db.update_exchange_settlement(sid3, "settled")
    bridge_db.update_exchange_settlement(sid4, "refunded")
    # locked + releasing reserve; settled + refunded do not.
    assert bridge_db.get_exchange_pending_eth_reserve() == Decimal("0.003")
