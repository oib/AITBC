"""#2840: /v1/exchange/history and /exchange/price.json must not 500 or emit
'NaN' when oracle prices are zero / NaN / infinite."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from aitbc.oracles.price_oracle import PriceResult
from apps.exchange.simple_exchange.handlers.exchange import ExchangeMixin


def _result(price, base="X", quote="USD"):
    return PriceResult(base=base, quote=quote, price=Decimal(str(price)), source="test", timestamp=1.0)


class _Oracle:
    def __init__(self, prices):
        self._prices = prices

    def get_price(self, base, quote="USD"):
        return self._prices.get((base, quote))


def _handler(prices):
    handler = MagicMock(spec=ExchangeMixin)
    handler.send_json_response = MagicMock()
    handler.send_error = MagicMock()
    handler.handle_exchange_history = ExchangeMixin.handle_exchange_history.__get__(handler, ExchangeMixin)
    handler.handle_exchange_price_json = ExchangeMixin.handle_exchange_price_json.__get__(handler, ExchangeMixin)
    return handler, _Oracle(prices)


def _responded(handler):
    assert handler.send_json_response.called, "no JSON response emitted"
    return handler.send_json_response.call_args[0][0]


GOOD = {
    ("ETH", "USD"): _result("3000"),
    ("ETH", "EUR"): _result("2700"),
    ("AIT", "USD"): _result("0.5"),
    ("AIT", "EUR"): None,
    ("AIT", "ETH"): _result("0.000166"),
}


class TestExchangeHistory:
    def test_zero_denominator_does_not_500(self):
        prices = {**GOOD, ("ETH", "USD"): _result("0")}
        handler, oracle = _handler(prices)
        with patch("aitbc.oracles.price_oracle.get_price_oracle", return_value=oracle):
            handler.handle_exchange_history(None)
        body = _responded(handler)
        assert body["success"] is True
        assert body["current"]["ait_eur"] is None
        assert body["current"]["eth_ait_rate_usd"] == 0

    def test_nan_prices_do_not_500_or_serialize_nan(self):
        prices = {**GOOD, ("AIT", "USD"): _result("nan"), ("ETH", "USD"): _result("nan")}
        handler, oracle = _handler(prices)
        with patch("aitbc.oracles.price_oracle.get_price_oracle", return_value=oracle):
            handler.handle_exchange_history(None)
        body = _responded(handler)
        assert body["success"] is True
        current = body["current"]
        for key in ("eth_usd", "ait_usd", "eth_eur", "ait_eur", "eth_ait_rate_usd"):
            value = current[key]
            assert value is None or value == 0 or (isinstance(value, Decimal) and value.is_finite())
        assert "NaN" not in str(body)

    def test_normal_prices_still_derive(self):
        handler, oracle = _handler(GOOD)
        with patch("aitbc.oracles.price_oracle.get_price_oracle", return_value=oracle):
            handler.handle_exchange_history(None)
        body = _responded(handler)
        assert body["success"] is True
        # ait_eur derived: 0.5 * 2700 / 3000 = 0.45
        assert body["current"]["ait_eur"] == Decimal("0.45")
        assert body["current"]["eth_ait_rate_usd"] == Decimal(3000) / Decimal("0.5")


class TestPriceJson:
    def test_nan_primary_falls_back_cleanly(self):
        prices = {("AIT", "USD"): _result("nan"), ("AIT", "EUR"): _result("0.45")}
        handler, oracle = _handler(prices)
        with patch("aitbc.oracles.price_oracle.get_price_oracle", return_value=oracle):
            handler.handle_exchange_price_json()
        body = _responded(handler)
        assert body["price_usd"] is None
        assert body["price_eur"] == Decimal("0.45")
        assert "NaN" not in str(body)

    def test_all_nan_is_503_not_nan_payload(self):
        prices = {("AIT", "USD"): _result("nan"), ("AIT", "EUR"): _result("inf")}
        handler, oracle = _handler(prices)
        with patch("aitbc.oracles.price_oracle.get_price_oracle", return_value=oracle):
            handler.handle_exchange_price_json()
        body = _responded(handler)
        assert body == {"error": "Price unavailable"}
        assert handler.send_json_response.call_args[1].get("status") == 503
