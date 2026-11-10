"""#1678: exchange mutating routes outside the signed-order paths are bounded.

Before this change only order placement, node register/payout and the read
endpoints had ``_rate_limit_hit`` buckets — POST /api/orders/{id}/cancel,
the marketplace mutations, the bridge mutations and /api/wallet/connect were
unlimited. These pins drive the real handlers with tiny per-minute budgets
and assert the 429 fires before the expensive work (body read / verify /
wallet lookup) runs.
"""

from unittest.mock import MagicMock

import pytest

from apps.exchange.simple_exchange.handlers import base as base_mod
from apps.exchange.simple_exchange.handlers.bridge import BridgeMixin
from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin
from apps.exchange.simple_exchange.handlers.market import MarketMixin


@pytest.fixture(autouse=True)
def _reset_buckets(monkeypatch):
    monkeypatch.setenv("EXCHANGE_MUTATING_PER_MIN", "2")
    monkeypatch.setenv("EXCHANGE_MAX_ORDERS_PER_MIN", "2")
    # test_http_contract's module fixture leaves this "0" in os.environ —
    # the cancel route 404s before reaching the limiter without it.
    monkeypatch.setenv("EXCHANGE_REQUIRE_SIGNED_ORDERS", "1")
    with base_mod._RATE_LOCK:
        base_mod._RATE_BUCKETS.clear()


def _handler() -> MagicMock:
    """Plain mock handler — module-level helpers read attrs via getattr."""
    h = MagicMock()
    h._client_ip = MagicMock(return_value="198.51.100.7")
    h.request = None
    h.send_json_response = MagicMock()
    h.send_error = MagicMock()
    return h


def _statuses(handler) -> list:
    return [c.kwargs.get("status") for c in handler.send_json_response.call_args_list]


def test_market_create_offer_rate_limited() -> None:
    h = _handler()
    h._require_api_key = MagicMock(return_value=False)
    h._read_json_body = MagicMock(return_value={})
    bound = MarketMixin.handle_market_create_offer.__get__(h, MarketMixin)

    bound()  # under budget -> reaches the API-key check
    bound()
    bound()  # third hit inside the window -> 429 before any work

    assert _statuses(h)[-1] == 429
    # The limiter fired before auth/body: the key check ran only twice.
    assert h._require_api_key.call_count == 2


def test_market_delete_offer_rate_limited() -> None:
    h = _handler()
    h._require_api_key = MagicMock(return_value=False)
    parsed = MagicMock()
    parsed.path = "/v1/market/offers/of-1"
    parsed.query = "wallet=0xw"
    bound = MarketMixin.handle_market_delete_offer.__get__(h, MarketMixin)

    bound(parsed)
    bound(parsed)
    bound(parsed)

    assert _statuses(h)[-1] == 429
    assert h._require_api_key.call_count == 2


def test_bridge_deposit_rate_limited() -> None:
    h = _handler()
    h._require_api_key = MagicMock(return_value=False)
    bound = BridgeMixin.handle_bridge_deposit.__get__(h, BridgeMixin)

    bound()
    bound()
    bound()

    assert _statuses(h)[-1] == 429
    assert h._require_api_key.call_count == 2


def test_wallet_connect_rate_limited() -> None:
    h = _handler()
    h._require_api_key = MagicMock(return_value=False)
    h._read_json_body = MagicMock(return_value={})
    bound = ExchangeMixin.handle_wallet_connect.__get__(h, ExchangeMixin)

    bound()
    bound()
    bound()

    assert _statuses(h)[-1] == 429
    assert h._require_api_key.call_count == 2


def test_cancel_order_ip_bucket_fires_before_verify() -> None:
    """Signed cancel: the per-IP bucket runs before the body is read — the
    expensive secp256k1 verify never sees a flooded request."""
    h = _handler()
    h._read_json_body = MagicMock(return_value={"envelope": {}, "signature": "0x"})
    h._verify_signed_body = MagicMock(return_value=None)  # verify "fails" cleanly
    bound = ExchangeMixin.handle_cancel_order.__get__(h, ExchangeMixin)

    bound("1")
    bound("1")
    bound("1")

    assert _statuses(h)[-1] == 429
    # _read_json_body only ran for the two requests inside the budget.
    assert h._read_json_body.call_count == 2
