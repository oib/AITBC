"""Unit tests for aitbc.agent_economics cross-chain swaps (v0.13.0 §A4)."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from aitbc.agent_economics import (
    CrossChainSwap,
    SwapError,
    SwapQuote,
    SwapRoute,
    SwapStatus,
    quote_swap,
)


def test_swap_route_net_output() -> None:
    route = SwapRoute(
        source_chain="ait-hub",
        target_chain="island-2",
        token="AITBC",
        amount=Decimal("100"),
        expected_output=Decimal("98"),
        fees=Decimal("1"),
    )
    assert route.net_output == Decimal("97")


def test_quote_swap_totals() -> None:
    route1 = SwapRoute(
        source_chain="ait-hub",
        target_chain="island-2",
        token="AITBC",
        amount=Decimal("100"),
        expected_output=Decimal("98"),
        fees=Decimal("1"),
    )
    route2 = SwapRoute(
        source_chain="island-2",
        target_chain="island-3",
        token="AITBC",
        amount=Decimal("98"),
        expected_output=Decimal("97"),
        fees=Decimal("1"),
    )
    quote = quote_swap("q1", "agent-a", [route1, route2])
    assert quote.total_amount == Decimal("198")
    assert quote.total_expected_output == Decimal("195")
    assert quote.total_fees == Decimal("2")
    assert quote.total_net_output == Decimal("193")


def test_cross_chain_swap_lifecycle() -> None:
    route = SwapRoute(
        source_chain="ait-hub",
        target_chain="island-2",
        token="AITBC",
        amount=Decimal("100"),
        expected_output=Decimal("98"),
        fees=Decimal("1"),
    )
    swap = CrossChainSwap(swap_id="s1", agent_id="agent-a")
    swap.add_route(route)
    assert len(swap.routes) == 1

    quote = quote_swap("q1", "agent-a", swap.routes)
    swap.set_quote(quote)
    assert swap.status == SwapStatus.QUOTED

    swap.execute()
    assert swap.status == SwapStatus.EXECUTED
    assert swap.executed_at is not None


def test_cannot_execute_without_quote() -> None:
    swap = CrossChainSwap(swap_id="s1", agent_id="agent-a")
    with pytest.raises(SwapError):
        swap.execute()


def test_quote_expiry_blocks_execution() -> None:
    route = SwapRoute(
        source_chain="ait-hub",
        target_chain="island-2",
        token="AITBC",
        amount=Decimal("100"),
        expected_output=Decimal("98"),
        fees=Decimal("1"),
    )
    swap = CrossChainSwap(swap_id="s1", agent_id="agent-a")
    swap.add_route(route)
    quote = SwapQuote(
        quote_id="q1",
        agent_id="agent-a",
        routes=swap.routes,
        expiry=datetime.utcnow() - timedelta(minutes=1),
    )
    swap.set_quote(quote)
    with pytest.raises(SwapError):
        swap.execute()
