"""ISLAND-ORDERS-CANCEL-1: a sealed cancel closes its order in the read model."""

from aitbc_cli.commands.exchange_island import _apply_cancels

BUY = {
    "sender": "0xabc",
    "payload": {
        "action": "buy",
        "order_id": "exchange_buy_1",
        "user_id": "0xabc",
        "pair": "AIT/ETH",
        "side": "buy",
        "amount": "10",
        "status": "open",
    },
}
CANCEL = {
    "sender": "0xabc",
    "payload": {
        "action": "cancel",
        "order_id": "exchange_buy_1",
        "user_id": "0xabc",
        "status": "cancelled",
    },
}


def _fresh():
    import copy

    return [copy.deepcopy(BUY), copy.deepcopy(CANCEL)]


def test_cancel_marks_order_cancelled():
    rows, ids = _apply_cancels(_fresh())
    assert "exchange_buy_1" in ids
    assert rows[0]["payload"]["status"] == "cancelled"


def test_cancel_row_is_dropped_order_keeps_its_fields():
    """#2400: cancel rows never survive into the read model — the order
    keeps its own pair/side and only its status flips."""
    rows, _ = _apply_cancels(_fresh())
    assert len(rows) == 1
    p = rows[0]["payload"]
    assert p["status"] == "cancelled"
    assert p["pair"] == "AIT/ETH" and p["side"] == "buy"


def test_double_cancel_idempotent():
    rows = _fresh() + [dict(CANCEL)]
    rows, ids = _apply_cancels(rows)
    assert ids == {"exchange_buy_1"}
    assert rows[0]["payload"]["status"] == "cancelled"


def test_cancel_for_unknown_order_is_ignored():
    import copy

    rows = [copy.deepcopy(CANCEL)]
    out, ids = _apply_cancels(rows)
    assert ids == set()  # #2501: only honoured cancels are recorded
    assert out == []  # the lone cancel row is dropped (#2400)


def test_cancel_marks_all_rows_with_same_order_id():
    """NITS-B-1: a duplicated order_id owned by the cancelling sender —
    every matching row is cancelled; the cancel row itself is dropped
    (#2400)."""
    import copy

    buy1 = {
        "sender": "0xabc",
        "payload": {"action": "buy", "order_id": "o1", "pair": "AIT/ETH", "side": "buy", "status": "open"},
    }
    buy2 = {
        "sender": "0xabc",
        "payload": {"action": "buy", "order_id": "o1", "pair": "AIT/EUR", "side": "buy", "status": "open"},
    }
    cancel = {
        "sender": "0xabc",
        "payload": {"action": "cancel", "order_id": "o1", "status": "cancelled"},
    }
    rows, ids = _apply_cancels([copy.deepcopy(buy1), copy.deepcopy(buy2), copy.deepcopy(cancel)])
    assert ids == {"o1"}
    assert len(rows) == 2
    assert rows[0]["payload"]["status"] == "cancelled"
    assert rows[1]["payload"]["status"] == "cancelled"


# ------------------------------------------------------------------ #2501


def test_foreign_sender_cancel_is_ignored():
    """#2501: order_ids are public — a cancel signed by a different wallet
    must not flip the victim's order, even when payload.user_id is forged
    to match."""
    import copy

    foreign_cancel = {
        "sender": "0xmallory",
        "payload": {
            "action": "cancel",
            "order_id": "exchange_buy_1",
            "user_id": "0xabc",  # attacker claims the victim's id
            "status": "cancelled",
        },
    }
    rows, ids = _apply_cancels([copy.deepcopy(BUY), foreign_cancel])
    assert ids == set()
    assert rows[0]["payload"]["status"] == "open"


def test_cancel_without_sender_is_ignored():
    """#2501 fail-closed: a row with no tx-level sender cannot prove
    ownership — the cancel is dropped, the order survives."""
    import copy

    senderless = copy.deepcopy(CANCEL)
    del senderless["sender"]
    rows, ids = _apply_cancels([copy.deepcopy(BUY), senderless])
    assert ids == set()
    assert rows[0]["payload"]["status"] == "open"


def test_sender_comparison_is_case_insensitive():
    import copy

    cancel = copy.deepcopy(CANCEL)
    cancel["sender"] = "0xABC"
    rows, ids = _apply_cancels([copy.deepcopy(BUY), cancel])
    assert ids == {"exchange_buy_1"}
    assert rows[0]["payload"]["status"] == "cancelled"


def test_foreign_cancel_on_flat_row_shape():
    """Flat rows (payload fields at top level, no 'payload' key) get the
    same sender binding — sender is read off the row itself."""
    order = {
        "sender": "0xalice",
        "action": "sell",
        "order_id": "o-flat",
        "status": "open",
    }
    foreign = {
        "sender": "0xbob",
        "action": "cancel",
        "order_id": "o-flat",
        "status": "cancelled",
    }
    rows, ids = _apply_cancels([order, foreign])
    assert ids == set()
    assert rows[0]["status"] == "open"


# ------------------------------------------------------------------ #2511


def _cancel_tx(sender, oid="exchange_buy_1"):
    return {
        "sender": sender,
        "payload": {
            "action": "cancel",
            "order_id": oid,
            "user_id": sender,
            "status": "cancelled",
        },
    }


def test_newer_foreign_cancel_does_not_shadow_own_cancel():
    """#2511: rows arrive newest-first — a foreign cancel posted after the
    owner's must not hide the owner's earlier valid cancel and resurrect
    the order."""
    import copy

    rows = [
        _cancel_tx("0xmallory"),  # newest: foreign, ignored
        _cancel_tx("0xabc"),  # owner's own cancel
        copy.deepcopy(BUY),
    ]
    out, ids = _apply_cancels(rows)
    assert ids == {"exchange_buy_1"}
    assert out[0]["payload"]["status"] == "cancelled"


def test_newer_own_cancel_still_cancels_over_older_foreign():
    """#2511 symmetric case: own cancel newest, foreign older — the order
    is cancelled by the own row regardless of order."""
    import copy

    rows = [
        _cancel_tx("0xabc"),
        _cancel_tx("0xmallory"),
        copy.deepcopy(BUY),
    ]
    out, ids = _apply_cancels(rows)
    assert ids == {"exchange_buy_1"}
    assert out[0]["payload"]["status"] == "cancelled"


def test_only_foreign_cancels_leave_order_open():
    """#2511: multiple foreign cancels and no own cancel — order survives."""
    import copy

    rows = [
        _cancel_tx("0xmallory"),
        _cancel_tx("0xeve"),
        copy.deepcopy(BUY),
    ]
    out, ids = _apply_cancels(rows)
    assert ids == set()
    assert out[0]["payload"]["status"] == "open"
