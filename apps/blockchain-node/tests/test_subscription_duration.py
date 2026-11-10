"""#1703: client-requested lease durations are validated and bounded.

``/rpc/subscribe`` and ``/rpc/heartbeat`` used to pass ``duration`` straight
through to the lease tracker: a non-numeric value surfaced as a 500 inside
``time.time() + duration`` and an arbitrarily large integer pinned an
effectively eternal lease. ``_bounded_lease_duration`` now rejects bad types
with 400 and clamps to ``settings.subscription_max_lease_duration``.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from aitbc_chain.config import settings
from aitbc_chain.rpc import subscription as subscription_module


def test_bounded_lease_duration_none_means_default() -> None:
    assert subscription_module._bounded_lease_duration(None) is None


def test_bounded_lease_duration_accepts_int_and_float() -> None:
    assert subscription_module._bounded_lease_duration(3600) == 3600
    assert subscription_module._bounded_lease_duration(3600.9) == 3600


@pytest.mark.parametrize("bad", ["3600", "abc", True, [1], {"s": 1}])
def test_bounded_lease_duration_rejects_non_numeric(bad: object) -> None:
    with pytest.raises(HTTPException) as exc:
        subscription_module._bounded_lease_duration(bad)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("bad", [0, -5, -0.5])
def test_bounded_lease_duration_rejects_non_positive(bad: float) -> None:
    with pytest.raises(HTTPException) as exc:
        subscription_module._bounded_lease_duration(bad)
    assert exc.value.status_code == 400


def test_bounded_lease_duration_clamps_to_max(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "subscription_max_lease_duration", 7200)
    assert subscription_module._bounded_lease_duration(10**12) == 7200
    assert subscription_module._bounded_lease_duration(7200) == 7200
    assert subscription_module._bounded_lease_duration(60) == 60


@pytest.mark.asyncio
async def test_register_subscription_clamps_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    """The register route hands the bounded value to the lease tracker."""
    monkeypatch.setattr(settings, "subscription_max_lease_duration", 7200)
    seen: dict[str, object] = {}

    async def _fake_register(
        node_id: str, transport: str, chain_id: str, duration: int | None = None, client_ip: str = "unknown"
    ) -> float:
        seen["duration"] = duration
        return 1234.0

    monkeypatch.setattr(subscription_module.lease_tracker, "register_subscriber", _fake_register)
    result = await subscription_module.register_subscription(
        {"node_id": "node-x", "duration": 10**12, "_client_ip": "10.0.0.1"}
    )
    assert seen["duration"] == 7200
    assert result["lease_duration"] == 7200


@pytest.mark.asyncio
async def test_register_subscription_rejects_bad_duration() -> None:
    with pytest.raises(HTTPException) as exc:
        await subscription_module.register_subscription({"node_id": "node-x", "duration": "forever"})
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_heartbeat_clamps_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "subscription_max_lease_duration", 7200)
    seen: dict[str, object] = {}

    async def _fake_extend(node_id: str, duration: int | None = None, **kwargs: object) -> float:
        seen["duration"] = duration
        return 5678.0

    monkeypatch.setattr(subscription_module.lease_tracker, "extend_lease", _fake_extend)
    result = await subscription_module.heartbeat({"node_id": "node-x", "duration": 10**9})
    assert seen["duration"] == 7200
    assert result["lease_duration"] == 7200


@pytest.mark.asyncio
async def test_heartbeat_rejects_bad_duration() -> None:
    with pytest.raises(HTTPException) as exc:
        await subscription_module.heartbeat({"node_id": "node-x", "duration": object()})
    assert exc.value.status_code == 400
