"""ISLAND-ORDERS-CANCEL-1: a sealed cancel closes its order in the read model."""

from aitbc_cli.commands.exchange_island import _apply_cancels

BUY = {
    "payload": {
        "action": "buy",
        "order_id": "exchange_buy_1",
        "user_id": "0xabc",
        "pair": "AIT/ETH",
        "side": "buy",
        "amount": "10",
        "status": "open",
    }
}
CANCEL = {
    "payload": {
        "action": "cancel",
        "order_id": "exchange_buy_1",
        "user_id": "0xabc",
        "status": "cancelled",
    }
}


def _fresh():
    import copy

    return [copy.deepcopy(BUY), copy.deepcopy(CANCEL)]


def test_cancel_marks_order_cancelled():
    rows, ids = _apply_cancels(_fresh())
    assert "exchange_buy_1" in ids
    assert rows[0]["payload"]["status"] == "cancelled"


def test_cancel_row_gets_pair_and_side():
    rows, _ = _apply_cancels(_fresh())
    c = rows[1]["payload"]
    assert c["pair"] == "AIT/ETH" and c["side"] == "buy"


def test_double_cancel_idempotent():
    rows = _fresh() + [dict(CANCEL)]
    rows, ids = _apply_cancels(rows)
    assert ids == {"exchange_buy_1"}
    assert rows[0]["payload"]["status"] == "cancelled"


def test_cancel_for_unknown_order_is_ignored():
    import copy

    rows = [copy.deepcopy(CANCEL)]
    out, ids = _apply_cancels(rows)
    assert ids == {"exchange_buy_1"}  # recorded but nothing to mark
    assert out[0]["payload"]["status"] == "cancelled"  # unchanged


def test_cancel_marks_all_rows_with_same_order_id():
    """NITS-B-1: a duplicated order_id — every matching row is cancelled
    and the fill uses the first."""
    import copy

    buy1 = {"payload": {"action": "buy", "order_id": "o1", "pair": "AIT/ETH", "side": "buy", "status": "open"}}
    buy2 = {"payload": {"action": "buy", "order_id": "o1", "pair": "AIT/EUR", "side": "buy", "status": "open"}}
    cancel = {"payload": {"action": "cancel", "order_id": "o1", "status": "cancelled"}}
    rows, ids = _apply_cancels([copy.deepcopy(buy1), copy.deepcopy(buy2), copy.deepcopy(cancel)])
    assert rows[0]["payload"]["status"] == "cancelled"
    assert rows[1]["payload"]["status"] == "cancelled"
    assert rows[2]["payload"]["pair"] == "AIT/ETH"
