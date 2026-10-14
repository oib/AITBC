"""Handler-level coverage for ETH-11 phase 2 internals (design section 12).

These exercise the paths that need a stubbed oracle or direct DB control —
band edges, stale feed, self-match, matching attribution, lazy expiry,
open-order caps, watchlist flagging — following the bound-method-on-MagicMock
convention from test_tick_matching.py.

All keys are throwaway test keys; no real wallet material or RPC endpoint is
touched.
"""

import sqlite3
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from eth_account import Account

from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin


@pytest.fixture(autouse=True)
def _chain_env(monkeypatch):
    """Pin the envelope chain_id — os.environ set by other test modules is
    process-global and would otherwise leak a different chain_id here."""
    monkeypatch.setenv("EXCHANGE_CHAIN_ID", "ait-localnet")
    monkeypatch.delenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", raising=False)
    monkeypatch.delenv("EXCHANGE_PRICE_BAND_PCT", raising=False)
    # Rate-limit buckets live on the module object — which test_http_contract's
    # sys.modules purge can duplicate — so rather than clear a possibly-stale
    # module's dict, just raise every window past what a test can spend.
    monkeypatch.setenv("EXCHANGE_MAX_ORDERS_PER_MIN", "100000")
    monkeypatch.setenv("EXCHANGE_REGISTER_PER_MIN", "100000")
    monkeypatch.setenv("EXCHANGE_READS_PER_MIN", "100000")


@pytest.fixture
def pair_keys():
    """Two throwaway node keys — seller + buyer."""
    a, b = Account.create(), Account.create()
    return (a.address, a.key.hex()), (b.address, b.key.hex())


def _sign(envelope, privkey):
    from aitbc.crypto.crypto import sign_transaction_data

    return sign_transaction_data(envelope, privkey)


def _seed_and_register(db_path, address, privkey, label, head=1000):
    """Seed a registry row then run the real signed registration path."""
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO node_registry (address, label, status) VALUES (?, ?, 'seeded')", (address, label))
    conn.commit()
    conn.close()
    h = _handler()
    env = {
        "action": "exchange_register",
        "address": address,
        "label": label,
        "account_nonce": 0,
        "chain_id": "ait-localnet",
    }
    body = {"envelope": env, "signature": _sign(env, privkey), "user_address": address}
    h._read_json_body = MagicMock(return_value=body)
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=db_path):
        h.handle_node_register()
    if h.send_error.called or (
        h.send_json_response.called and h.send_json_response.call_args[0][0].get("status") != "registered"
    ):
        raise AssertionError(f"seed register failed: {h.send_error.call_args_list} {h.send_json_response.call_args_list}")
    return h


def _handler():
    """Spec'd mock with the phase-2 methods bound to the real implementations."""
    h = MagicMock(spec=ExchangeMixin)
    h.send_error = MagicMock()
    h.send_json_response = MagicMock()
    h._client_ip = MagicMock(return_value="127.0.0.1")
    for name in (
        "handle_node_register",
        "handle_place_order",
        "handle_cancel_order",
        "handle_my_orders",
        "handle_exchange_nodes",
        "_place_order_signed",
        "_place_order_unsigned",
        "_verify_signed_body",
        "_order_envelope_error",
        "_cancel_envelope_error",
        "_live_head_if_unexpired",
        "_signed_order_limits",
        "_book_capacity_error",
        "_commit_signed_order",
        "_signed_order_gate",
        "_insert_signed_order",
        "_match_orders_in_txn",
        "_expire_open_orders",
        "_commit_register",
        "_commit_cancel",
        "_registry_status",
        "_registry_labels",
        "_expected_nonce",
        "_claim_nonce",
        "_order_by_envelope",
        "_chain_head_height",
        "_ait_eth_band",
        "_ait_eth_rate",
        "get_orderbook",
        "get_recent_trades",
        "_orderbook_row",
        "_watchlisted_addresses",
        "_node_rows",
    ):
        if hasattr(ExchangeMixin, name):
            attr = getattr(ExchangeMixin, name)
            # staticmethods take no self — assign raw; methods bind to h.
            if name in ("_expected_nonce", "_claim_nonce", "_expire_open_orders", "_watchlisted_addresses"):
                setattr(h, name, attr)
            else:
                setattr(h, name, attr.__get__(h, ExchangeMixin))
    return h


def _order_body(addr, key, *, side="SELL", amount=10, price="0.001", expiry=2000, nonce=1):
    env = {
        "side": side,
        "pair": "AIT/ETH",
        "amount_ticks": int(Decimal(amount) * 100_000_000),
        "price_ticks": int(Decimal(price) * 100_000_000),
        "expiry_height": expiry,
        "account_nonce": nonce,
        "chain_id": "ait-localnet",
    }
    return {"envelope": env, "signature": _sign(env, key), "user_address": addr}


def _place(db_path, h, body, head=1000):
    h._read_json_body = MagicMock(return_value=body)
    h.send_error.reset_mock()
    h.send_json_response.reset_mock()
    with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=db_path):
        h.handle_place_order()


def _last_json(h):
    assert h.send_json_response.called, f"no response; send_error={h.send_error.call_args_list}"
    return h.send_json_response.call_args[0][0]


# --- price band (design section 3) ----------------------------------------


class TestPriceBand:
    def test_inside_band_accepted(self, exchange_db, pair_keys):
        (addr, key), _ = pair_keys
        _seed_and_register(exchange_db, addr, key, "n-in")
        h = _handler()
        h._ait_eth_band = MagicMock(return_value=(Decimal("0.0009"), Decimal("0.0011")))
        h._chain_head_height = MagicMock(return_value=1000)
        _place(exchange_db, h, _order_body(addr, key, price="0.001"))
        assert _last_json(h)["status"] == "open"

    def test_outside_band_rejected(self, exchange_db, pair_keys):
        (addr, key), _ = pair_keys
        _seed_and_register(exchange_db, addr, key, "n-out")
        h = _handler()
        h._ait_eth_band = MagicMock(return_value=(Decimal("0.0009"), Decimal("0.0011")))
        h._chain_head_height = MagicMock(return_value=1000)
        _place(exchange_db, h, _order_body(addr, key, price="0.0015"))
        h.send_error.assert_called_once()
        assert h.send_error.call_args[0][0] == 400

    def test_stale_feed_503(self, exchange_db, pair_keys):
        """Band unavailable → 503 like the quote endpoint (design section 3)."""
        (addr, key), _ = pair_keys
        _seed_and_register(exchange_db, addr, key, "n-stale")
        h = _handler()
        h._ait_eth_band = MagicMock(return_value=None)
        h._chain_head_height = MagicMock(return_value=1000)
        _place(exchange_db, h, _order_body(addr, key))
        h.send_json_response.assert_called_once()
        assert h.send_json_response.call_args[1]["status"] == 503 or h.send_json_response.call_args[0][1] == 503


# --- matching: self-match, attribution, partial fill -----------------------


class TestMatching:
    def test_self_match_rejected(self, exchange_db, pair_keys):
        """Same-node buy against its own sell never fills (sections 6/9)."""
        (addr, key), _ = pair_keys
        _seed_and_register(exchange_db, addr, key, "n-self")
        h = _handler()
        h._ait_eth_band = MagicMock(return_value=(Decimal("0"), Decimal("1e18")))
        h._chain_head_height = MagicMock(return_value=1000)
        _place(exchange_db, h, _order_body(addr, key, side="SELL", price="0.001", nonce=1))
        assert _last_json(h)["status"] == "open"
        _place(exchange_db, h, _order_body(addr, key, side="BUY", price="0.001", nonce=2))
        doc = _last_json(h)
        assert doc["status"] == "open"  # no fill — the only counterparty was itself
        conn = sqlite3.connect(exchange_db)
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 0
        conn.close()

    def test_match_attributes_buyer_seller_and_fee(self, exchange_db, pair_keys):
        (sa, sk), (ba, bk) = pair_keys
        _seed_and_register(exchange_db, sa, sk, "n-sell")
        _seed_and_register(exchange_db, ba, bk, "n-buy")
        h = _handler()
        h._ait_eth_band = MagicMock(return_value=(Decimal("0"), Decimal("1e18")))
        h._chain_head_height = MagicMock(return_value=1000)
        _place(exchange_db, h, _order_body(sa, sk, side="SELL", amount=10, price="0.001", nonce=1))
        # buy only 4 of the 10 — partial fill
        _place(exchange_db, h, _order_body(ba, bk, side="BUY", amount=4, price="0.001", nonce=1))
        doc = _last_json(h)
        assert doc["status"] == "filled"
        conn = sqlite3.connect(exchange_db)
        trade = conn.execute("SELECT amount, buyer_address, seller_address, fee_ait FROM trades").fetchone()
        sell = conn.execute("SELECT remaining, status FROM orders WHERE order_type='SELL'").fetchone()
        conn.close()
        assert trade[0] == "4"
        assert trade[1] == ba and trade[2] == sa
        assert trade[3] is not None  # fee_ait recorded (default 0 on testnet)
        assert sell == ("6", "open")


# --- lazy expiry ------------------------------------------------------------


class TestLazyExpiry:
    def test_expired_open_order_flips_at_match_scan(self, exchange_db, pair_keys):
        (sa, sk), (ba, bk) = pair_keys
        _seed_and_register(exchange_db, sa, sk, "n-exp")
        _seed_and_register(exchange_db, ba, bk, "n-exp-buy")
        h = _handler()
        h._ait_eth_band = MagicMock(return_value=(Decimal("0"), Decimal("1e18")))
        # head=1000; sell expires at 900
        h._chain_head_height = MagicMock(return_value=1000)
        _place(exchange_db, h, _order_body(sa, sk, side="SELL", expiry=900, nonce=1), head=1000)
        # placement of an already-expired envelope must fail (no row inserted)
        h.send_json_response.assert_called()
        conn = sqlite3.connect(exchange_db)
        n = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        conn.close()
        assert n == 0

    def test_open_order_expired_by_later_head(self, exchange_db, pair_keys):
        (sa, sk), (ba, bk) = pair_keys
        _seed_and_register(exchange_db, sa, sk, "n-exp2")
        _seed_and_register(exchange_db, ba, bk, "n-exp2-buy")
        h = _handler()
        h._ait_eth_band = MagicMock(return_value=(Decimal("0"), Decimal("1e18")))
        h._chain_head_height = MagicMock(return_value=1000)
        _place(exchange_db, h, _order_body(sa, sk, side="SELL", expiry=1100, nonce=1))
        assert _last_json(h)["status"] == "open"
        # head advances past the sell's expiry; the next match scan expires it
        h._chain_head_height = MagicMock(return_value=1200)
        _place(exchange_db, h, _order_body(ba, bk, side="BUY", price="0.001", nonce=1))
        doc = _last_json(h)
        assert doc["status"] == "open"  # nothing to fill against
        conn = sqlite3.connect(exchange_db)
        sell = conn.execute("SELECT status FROM orders WHERE order_type='SELL'").fetchone()
        conn.close()
        assert sell[0] == "expired"


# --- caps and watchlist -----------------------------------------------------


class TestAbuseLimits:
    def test_open_order_cap_per_node(self, exchange_db, pair_keys, monkeypatch):
        monkeypatch.setenv("EXCHANGE_MAX_OPEN_PER_NODE", "2")
        (addr, key), _ = pair_keys
        _seed_and_register(exchange_db, addr, key, "n-cap")
        h = _handler()
        h._ait_eth_band = MagicMock(return_value=(Decimal("0"), Decimal("1e18")))
        h._chain_head_height = MagicMock(return_value=1000)
        for i, nonce in enumerate((1, 2, 3)):
            _place(exchange_db, h, _order_body(addr, key, side="SELL", price=f"0.00{i + 2}", nonce=nonce))
        # third place hit the cap — rejected inside the write transaction
        assert (
            h.send_json_response.call_args[1].get("status") == 429
            or "limit" in str(h.send_json_response.call_args[0][0]).lower()
        )
        conn = sqlite3.connect(exchange_db)
        assert conn.execute("SELECT COUNT(*) FROM orders WHERE status='open'").fetchone()[0] == 2
        conn.close()

    def test_watchlist_flags_high_cancel_ratio(self, exchange_db, pair_keys):
        """A node that cancels everything it places is flagged (section 9)."""
        (addr, key), _ = pair_keys
        _seed_and_register(exchange_db, addr, key, "n-watch")
        h = _handler()
        h._ait_eth_band = MagicMock(return_value=(Decimal("0"), Decimal("1e18")))
        h._chain_head_height = MagicMock(return_value=1000)
        # The flag only engages past a placement floor — place 10, cancel all.
        order_ids = []
        for i in range(10):
            _place(exchange_db, h, _order_body(addr, key, price=f"0.000{i + 1}", nonce=1 + i))
            order_ids.append(_last_json(h)["id"])
        for i, oid in enumerate(order_ids):
            cancel_env = {
                "action": "exchange_cancel",
                "order_id": oid,
                "expiry_height": 2000,
                "account_nonce": 11 + i,
                "chain_id": "ait-localnet",
            }
            h._read_json_body = MagicMock(
                return_value={
                    "envelope": cancel_env,
                    "signature": _sign(cancel_env, key),
                    "user_address": addr,
                }
            )
            h.send_json_response.reset_mock()
            with patch("apps.exchange.simple_exchange.handlers.exchange.get_db_path", return_value=exchange_db):
                h.handle_cancel_order(str(oid))
            assert _last_json(h)["status"] == "cancelled"

        conn = sqlite3.connect(exchange_db)
        cur = conn.cursor()
        from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin as EM

        flagged = EM._watchlisted_addresses(cur)
        conn.close()
        assert addr in flagged
