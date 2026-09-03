"""A reconciliation retry must not redate a settlement that already happened.

When the reconciler retries a release, `_submit_payment_tx` finds the ESCROW_RELEASE
that already settled the job and hands that same transaction back. The release then
looks fresh even though the provider was paid earlier, so `released_at` has to come
from the stored record rather than the clock.
"""

import asyncio
import importlib
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aitbc_chain.base_models import Escrow

# Deterministic, valid EIP-55 0x addresses.
# Derived via eth_account.Account.from_key(sha256(name.encode()).digest()).address
BUYER = "0xe8b0db006F34bf5b5d2B22553C017431E8e86e4F"
PROVIDER = "0xD4d85501E6cD447972Db19370307F1E3B1510016"

ORIGINAL = datetime(2026, 8, 23, 9, 20, 0, tzinfo=UTC)


def _reload_routes():
    from aitbc_chain.rpc import escrow_routes

    importlib.reload(escrow_routes)
    return escrow_routes


def _manager():
    contract = SimpleNamespace(
        milestones=[],
        state=None,
        released_amount=Decimal("0.975"),
        client_address=BUYER,
        agent_address=PROVIDER,
    )
    mgr = MagicMock()
    mgr.escrow_contracts = {"c-1": contract}
    mgr.release_lock.return_value = asyncio.Lock()
    mgr.snapshot_release_state.return_value = {"state": None}
    mgr.release_payment = AsyncMock(return_value=(True, "released"))
    return mgr


def _record(released_at):
    """A real Escrow row, not a stub of the two fields this test reads.

    The release route reads the row for its duplicate-release guards and for the
    settled amounts it echoes back, and it grew fields as metered settlement
    arrived. A SimpleNamespace carrying only ``released_at`` made each of those a
    silent AttributeError inside the guard's ``except``, which skipped the guard
    rather than failing the assertion that was meant to catch it.
    """
    return Escrow(
        job_id="job-1",
        chain_id="test-chain",
        buyer=BUYER,
        provider=PROVIDER,
        amount=36_000_000,
        status="locked",
        created_at=ORIGINAL,
        released_at=released_at,
    )


def _run_release(routes, record):
    @contextmanager
    def fake_scope():
        session = MagicMock()
        session.get.return_value = record
        yield session

    with (
        patch.object(routes, "get_escrow_manager", return_value=_manager()),
        patch.object(routes, "_find_contract_id", AsyncMock(return_value="c-1")),
        patch.object(routes, "_get_settlement_key", return_value="0x" + "22" * 32),
        patch.object(routes, "_get_settlement_address", return_value="0xabc"),
        patch.object(routes, "_submit_payment_tx", AsyncMock(return_value="0xdeadbeef")),
        patch.object(routes, "session_scope", fake_scope),
    ):
        return asyncio.run(routes.release_escrow("job-1", {}))


@pytest.mark.parametrize("stored", [ORIGINAL, ORIGINAL.replace(tzinfo=None)])
def test_retry_keeps_the_original_settlement_time(stored):
    """An escrow that already carries a settlement time keeps it, tz-aware or not."""
    routes = _reload_routes()
    record = _record(stored)

    result = _run_release(routes, record)

    assert result["success"] is True
    assert record.released_at == stored, "the stored settlement time was overwritten"
    assert result["released_at"] == stored.isoformat()


def test_first_release_stamps_the_current_time():
    """A genuine first release still records when it settled."""
    routes = _reload_routes()
    record = _record(None)
    before = datetime.now(UTC)

    result = _run_release(routes, record)

    assert record.released_at is not None
    assert record.released_at >= before
    assert result["released_at"] == record.released_at.isoformat()
