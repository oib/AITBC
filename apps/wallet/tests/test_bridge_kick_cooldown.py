"""#1079 pin: the deposit estimate's demand signal shares the per-IP poll-kick
cooldown with /poll-request — two kicks from one IP inside the cooldown
trigger one poll."""

from __future__ import annotations

import pytest

from wallet_app.bridge import bridge_routes


@pytest.fixture(autouse=True)
def _clean_kick_map(monkeypatch):
    monkeypatch.setattr(bridge_routes, "_kick_last_by_ip", {})
    yield


def test_second_kick_inside_cooldown_does_not_poll(monkeypatch):
    calls = []
    monkeypatch.setattr(bridge_routes, "_kick_bridge_poll", lambda: calls.append(1))
    first = bridge_routes._kick_for_ip("203.0.113.7")
    second = bridge_routes._kick_for_ip("203.0.113.7")
    assert first["kicked"] is True
    assert second["kicked"] is False
    assert second["retry_after_seconds"] > 0
    assert len(calls) == 1  # one poll, not two


def test_other_ip_and_cooldown_expiry_still_kick(monkeypatch):
    calls = []
    monkeypatch.setattr(bridge_routes, "_kick_bridge_poll", lambda: calls.append(1))
    assert bridge_routes._kick_for_ip("203.0.113.7")["kicked"] is True
    assert bridge_routes._kick_for_ip("203.0.113.8")["kicked"] is True
    bridge_routes._kick_last_by_ip["203.0.113.7"] -= bridge_routes._KICK_COOLDOWN_SECONDS + 1
    assert bridge_routes._kick_for_ip("203.0.113.7")["kicked"] is True
    assert len(calls) == 3


def test_deposit_estimate_kicks_once_per_ip_per_cooldown(monkeypatch):
    """Route-level pin: two /deposit estimate calls from one IP inside the
    cooldown must still trigger only one monitor poll (the estimate used to
    call _kick_bridge_poll directly, bypassing /poll-request's limit)."""
    import asyncio
    from decimal import Decimal

    from starlette.requests import Request

    calls = []
    monkeypatch.setattr(bridge_routes, "_kick_bridge_poll", lambda: calls.append(1))

    async def fake_ait_amount(eth):
        return Decimal("10")

    async def fake_rates():
        return {"success": False, "eth_ait_rate_usd": "1", "timestamp": "t"}

    monkeypatch.setattr(bridge_routes, "calculate_ait_amount", fake_ait_amount)
    monkeypatch.setattr(bridge_routes, "get_exchange_rate", fake_rates)
    monkeypatch.setenv("ETH_WALLET_ADDRESS", "0x" + "ee" * 20)
    monkeypatch.setattr(bridge_routes, "validate_address_strict", lambda a: a)

    def req():
        return Request({"type": "http", "method": "POST", "headers": {}, "client": ("203.0.113.9", 1), "query_string": b""})

    body = {"eth_amount": "0.01", "ait_address": "0x" + "ab" * 20}
    asyncio.run(bridge_routes.bridge_deposit(req(), dict(body)))
    asyncio.run(bridge_routes.bridge_deposit(req(), dict(body)))
    assert len(calls) == 1
