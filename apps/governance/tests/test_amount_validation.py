"""#1644: stake/delegate must reject non-positive amounts.

``stake_tokens`` feeds ``staked_tokens`` → ``calculate_voting_power`` and,
downstream, ``Vote.voting_power_used`` tallies. A negative amount drove both
negative — a vote could subtract from proposal tallies. ``delegate_voting_power``
only checked ``delegator_power < amount``, so zero/negative amounts passed.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from governance_service.services.governance_service import GovernanceService


class _Session:
    """Minimal AsyncSession stub: no token record exists for any address."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def execute(self, stmt):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: None, all=lambda: []))


@pytest.mark.asyncio
async def test_stake_rejects_negative_amount():
    svc = GovernanceService(session=_Session())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        await svc.stake_tokens("0xabc", -5, 30)


@pytest.mark.asyncio
async def test_stake_rejects_zero_amount():
    svc = GovernanceService(session=_Session())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        await svc.stake_tokens("0xabc", 0, 30)


@pytest.mark.asyncio
async def test_stake_rejects_negative_lock_period():
    svc = GovernanceService(session=_Session())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative"):
        await svc.stake_tokens("0xabc", 10, -1)


@pytest.mark.asyncio
async def test_delegate_rejects_negative_amount():
    svc = GovernanceService(session=_Session())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        await svc.delegate_voting_power("0xabc", "0xdef", -1)


@pytest.mark.asyncio
async def test_delegate_rejects_zero_amount():
    svc = GovernanceService(session=_Session())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive"):
        await svc.delegate_voting_power("0xabc", "0xdef", 0)


@pytest.mark.asyncio
async def test_stake_accepts_positive_amount():
    svc = GovernanceService(session=_Session())  # type: ignore[arg-type]
    stake = await svc.stake_tokens("0xabc", 10, 30)
    assert stake.amount_staked == 10
