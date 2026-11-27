"""#3051 (AUDIT-EXCHANGE-PEG-DRIFT-1): the two migrated copies of the
ETH->AITBC ``create-payment`` surface — coordinator-api's
``/v1/exchange/*`` and trading's ``exchange_compat`` router — must agree
on the peg, fee, and amount-match rule because they serve the same
logical operation to different clients.

These pins fail if either router re-declares the config locally or if
the shared source in ``aitbc.exchange_payment`` is bypassed: mutating the
shared constant must be visible through BOTH routers' rate output.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from starlette.requests import Request

from aitbc import exchange_payment


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/exchange/rates",
            "headers": [],
        }
    )


def _coordinator_exchange():
    from coordinator_api.contexts.infrastructure.routers import exchange as mod

    return mod


def _trading_exchange_compat():
    from trading_service.routers import exchange_compat as mod

    return mod


class TestSharedConfig:
    def test_canonical_values(self) -> None:
        # The coordinator's deliberate ETH peg — the trading copy's old
        # 100000 was a leftover BTC peg (1 BTC = 100,000 AITBC).
        assert exchange_payment.EXCHANGE_RATE_ETH_TO_AITBC == Decimal("1000")
        assert exchange_payment.EXCHANGE_MIN_CONFIRMATIONS == 12
        assert exchange_payment.EXCHANGE_PAYMENT_TIMEOUT_SECONDS == 3600
        assert exchange_payment.EXCHANGE_ETH_AMOUNT_TOLERANCE == Decimal("0.00000001")

    def test_both_router_config_dicts_match_shared_constants(self) -> None:
        coord = _coordinator_exchange()
        trading = _trading_exchange_compat()
        for cfg in (coord.ETH_CONFIG, trading.ETHEREUM_CONFIG):
            assert cfg["exchange_rate"] == exchange_payment.EXCHANGE_RATE_ETH_TO_AITBC
            assert cfg["min_confirmations"] == exchange_payment.EXCHANGE_MIN_CONFIRMATIONS
            assert cfg["payment_timeout"] == exchange_payment.EXCHANGE_PAYMENT_TIMEOUT_SECONDS

    def test_expected_eth_and_tolerance(self) -> None:
        ait = Decimal("2500.5")
        assert exchange_payment.expected_eth_amount(ait) == ait / Decimal("1000")
        # Within the 1e-8 ETH client tolerance -> accepted; outside -> rejected.
        expected = exchange_payment.expected_eth_amount(ait)
        assert exchange_payment.eth_amount_matches(ait, expected)
        assert exchange_payment.eth_amount_matches(ait, expected + exchange_payment.EXCHANGE_ETH_AMOUNT_TOLERANCE)
        assert not exchange_payment.eth_amount_matches(ait, expected + Decimal("0.001"))


class TestRatesParity:
    def test_rates_identical_for_same_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        coord = _coordinator_exchange()
        trading = _trading_exchange_compat()

        for fee in (None, "0.005", "nan", "-1"):
            if fee is None:
                monkeypatch.delenv("EXCHANGE_FEE_PCT", raising=False)
            else:
                monkeypatch.setenv("EXCHANGE_FEE_PCT", fee)

            coord_rates = coord.get_exchange_rates(_request())
            trading_rates = trading.get_exchange_rates()

            assert Decimal(str(coord_rates.eth_to_aitbc)) == Decimal(str(trading_rates["eth_to_aitbc"]))
            assert Decimal(str(coord_rates.aitbc_to_eth)) == Decimal(str(trading_rates["aitbc_to_eth"]))
            assert Decimal(str(coord_rates.fee_percent)) == Decimal(str(trading_rates["fee_percent"]))

    def test_mutation_of_shared_constant_reflected_by_both(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The peg is not a per-service constant: changing the shared value
        must change what BOTH routers report."""
        coord = _coordinator_exchange()
        trading = _trading_exchange_compat()

        monkeypatch.setattr(exchange_payment, "EXCHANGE_RATE_ETH_TO_AITBC", Decimal("7"))

        assert exchange_payment.expected_eth_amount(Decimal("70")) == Decimal("10")
        assert Decimal(str(coord.get_exchange_rates(_request()).eth_to_aitbc)) == Decimal("7")
        assert Decimal(str(trading.get_exchange_rates()["eth_to_aitbc"])) == Decimal("7")
