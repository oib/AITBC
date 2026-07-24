"""Unit tests for aitbc.agent_economics portfolio (v0.13.0 §A1)."""

from __future__ import annotations

from decimal import Decimal


from aitbc.agent_economics import ChainHoldings, Portfolio


def test_portfolio_total_value() -> None:
    portfolio = Portfolio(
        portfolio_id="p1",
        agent_id="agent-a",
        positions=[
            ChainHoldings(
                chain_id="ait-hub",
                token="AITBC",
                amount=Decimal("60"),
                target_percent=Decimal("50"),
                current_percent=Decimal("60"),
            ),
            ChainHoldings(
                chain_id="island-2",
                token="AITBC",
                amount=Decimal("40"),
                target_percent=Decimal("50"),
                current_percent=Decimal("40"),
            ),
        ],
    )
    assert portfolio.total_value == Decimal("100")
    assert portfolio.allocation("ait-hub", "AITBC") == Decimal("60")
    assert portfolio.allocation("island-2", "AITBC") == Decimal("40")


def test_portfolio_deviations() -> None:
    portfolio = Portfolio(
        portfolio_id="p1",
        agent_id="agent-a",
        positions=[
            ChainHoldings(
                chain_id="ait-hub",
                token="AITBC",
                amount=Decimal("70"),
                target_percent=Decimal("50"),
                current_percent=Decimal("70"),
            ),
            ChainHoldings(
                chain_id="island-2",
                token="AITBC",
                amount=Decimal("30"),
                target_percent=Decimal("50"),
                current_percent=Decimal("30"),
            ),
        ],
    )
    deviations = portfolio.deviations()
    assert deviations[("ait-hub", "AITBC")] == Decimal("20")
    assert deviations[("island-2", "AITBC")] == Decimal("-20")


def test_portfolio_rebalance_needed() -> None:
    portfolio = Portfolio(
        portfolio_id="p1",
        agent_id="agent-a",
        positions=[
            ChainHoldings(
                chain_id="ait-hub",
                token="AITBC",
                amount=Decimal("70"),
                target_percent=Decimal("50"),
                current_percent=Decimal("70"),
            ),
            ChainHoldings(
                chain_id="island-2",
                token="AITBC",
                amount=Decimal("30"),
                target_percent=Decimal("50"),
                current_percent=Decimal("30"),
            ),
        ],
    )
    flagged = portfolio.rebalance_needed(threshold=Decimal("5"))
    assert len(flagged) == 2


def test_portfolio_add_position_updates_existing() -> None:
    holdings = ChainHoldings(
        chain_id="ait-hub",
        token="AITBC",
        amount=Decimal("50"),
        target_percent=Decimal("50"),
        current_percent=Decimal("50"),
    )
    portfolio = Portfolio(
        portfolio_id="p1",
        agent_id="agent-a",
        positions=[holdings],
    )
    portfolio.add_position(
        ChainHoldings(
            chain_id="ait-hub",
            token="AITBC",
            amount=Decimal("10"),
            target_percent=Decimal("50"),
        )
    )
    assert portfolio.total_value == Decimal("60")
