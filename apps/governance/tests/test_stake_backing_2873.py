"""#2873: stake_tokens must refuse stakes the wallet cannot back on-chain.

Before the fix any signed caller could ``POST /v1/governance/stake`` an
arbitrary amount; ``staked_tokens`` fed ``calculate_voting_power``
(balance + 2×staked) with no balance check anywhere — ``token_balance``
has no writer, so voting power was entirely self-reported. These pins
assert the service now verifies the on-chain balance, caps cumulative
stakes at it, and fails closed when the chain cannot be queried.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from governance_service.services.governance_service import GovernanceService


class _Session:
    """Minimal AsyncSession stub that persists GovernanceToken rows so
    cumulative-stake accounting is exercised for real."""

    def __init__(self):
        self.added = []
        self._tokens = {}

    def add(self, obj):
        self.added.append(obj)
        from governance_service.domain.governance import GovernanceToken

        if isinstance(obj, GovernanceToken):
            self._tokens[obj.holder_address] = obj

    async def commit(self):
        pass

    async def refresh(self, obj):
        pass

    async def execute(self, stmt):
        from governance_service.domain.governance import GovernanceToken

        tokens = [t for t in self._tokens.values() if isinstance(t, GovernanceToken)]
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(first=lambda: tokens[0] if tokens else None, all=lambda: tokens)
        )


class _Chain:
    def __init__(self, balance):
        self.balance = balance
        self.calls = 0

    async def get_voting_power(self, address, chain_id=None):
        self.calls += 1
        if isinstance(self.balance, Exception):
            raise self.balance
        return self.balance


def _svc(balance) -> tuple[GovernanceService, _Chain]:
    chain = _Chain(balance)
    return GovernanceService(session=_Session(), blockchain_client=chain), chain  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_stake_within_balance_accepted():
    svc, _ = _svc(Decimal("100"))
    stake = await svc.stake_tokens("0xabc", 10, 30)
    assert stake.amount_staked == 10


@pytest.mark.asyncio
async def test_stake_exceeding_balance_rejected():
    svc, _ = _svc(Decimal("100"))
    with pytest.raises(ValueError, match="on-chain backing"):
        await svc.stake_tokens("0xabc", 101, 30)


@pytest.mark.asyncio
async def test_cumulative_stakes_cannot_exceed_balance():
    """Two stakes each under the balance must not combine past it."""
    svc, _ = _svc(Decimal("100"))
    await svc.stake_tokens("0xabc", 60, 30)
    with pytest.raises(ValueError, match="on-chain backing"):
        await svc.stake_tokens("0xabc", 60, 30)


@pytest.mark.asyncio
async def test_zero_balance_rejects_any_stake():
    svc, _ = _svc(Decimal("0"))
    with pytest.raises(ValueError, match="on-chain backing"):
        await svc.stake_tokens("0xabc", 1, 30)


@pytest.mark.asyncio
async def test_chain_error_fails_closed():
    svc, _ = _svc(ConnectionError("rpc down"))
    with pytest.raises(ValueError, match="cannot verify on-chain balance"):
        await svc.stake_tokens("0xabc", 1, 30)
