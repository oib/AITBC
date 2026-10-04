"""Tests for the IPFS rental escrow lifecycle sweeper.

These tests cover:
- Expired active rentals are marked expired and the escrow is released to the provider.
- Rentals with ``status == "refund_pending"`` are refunded instead of released.
- Rentals that were never pinned are refunded.
- Addresses are canonicalized to 0x EIP-55 before on-chain calls.
"""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from market_service.domain.market import IpfsRentalToken
from market_service.services.ipfs_rental_sweeper import IpfsRentalSweeper
from market_service.storage import get_session_context


class FakeBlockchainRPCClient:
    """In-memory RPC client that records release/refund calls."""

    def __init__(self) -> None:
        self.released: list[str] = []
        self.refunded: list[str] = []

    async def release_escrow(self, job_id: str) -> dict[str, Any] | None:
        self.released.append(job_id)
        return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    async def refund_escrow(self, job_id: str) -> dict[str, Any] | None:
        self.refunded.append(job_id)
        return {"success": True, "tx_hash": f"0xrefund_{job_id}"}

    async def verify_escrow(self, job_id: str) -> dict[str, Any] | None:
        return {"job_id": job_id, "status": "locked"}


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Provide a fresh async session for each test."""
    async with get_session_context() as session:
        yield session


@asynccontextmanager
async def _session_factory() -> AsyncIterator[AsyncSession]:
    async with get_session_context() as session:
        yield session


async def test_sweeper_releases_expired_pinned_rental(session: AsyncSession) -> None:
    """A pinned rental past its expiration has its escrow released to the provider."""
    now = datetime.now(UTC)
    buyer = "0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76"
    provider = "0x241D3e44d42b6d4c270d0231780913f14386d90C"
    token = IpfsRentalToken(
        access_key="ak_release",
        access_secret="secret",
        rental_id="ipfs_rental_001",
        offer_id="offer-1",
        cid="QmTest",
        buyer_address=buyer.lower(),
        provider_address=provider.lower(),
        escrow_contract_id="ipfs_rental_001",
        pinned=True,
        status="active",
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(hours=1),
        updated_at=now - timedelta(days=2),
    )
    session.add(token)
    await session.commit()

    rpc = FakeBlockchainRPCClient()
    sweeper = IpfsRentalSweeper(
        interval_seconds=3600,
        batch_size=10,
        refund_grace_seconds=0,
        rpc_client=rpc,
        session_factory=_session_factory,
    )
    await sweeper.sweep_once()

    await session.refresh(token)
    assert token.status == "released"
    assert token.tx_hash == "0xrelease_ipfs_rental_001"
    assert token.buyer_address == buyer
    assert token.provider_address == provider
    assert rpc.released == ["ipfs_rental_001"]
    assert rpc.refunded == []


async def test_sweeper_refunds_unpinned_rental(session: AsyncSession) -> None:
    """A rental that was never pinned is refunded to the buyer."""
    now = datetime.now(UTC)
    token = IpfsRentalToken(
        access_key="ak_refund",
        access_secret="secret",
        rental_id="ipfs_rental_002",
        offer_id="offer-2",
        cid="QmTest2",
        buyer_address="0xab0797ae8cff09b313c71cab2f894b342b6e1d76",
        provider_address="0x241d3e44d42b6d4c270d0231780913f14386d90c",
        escrow_contract_id="ipfs_rental_002",
        pinned=False,
        status="active",
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(hours=1),
        updated_at=now - timedelta(days=2),
    )
    session.add(token)
    await session.commit()

    rpc = FakeBlockchainRPCClient()
    sweeper = IpfsRentalSweeper(
        interval_seconds=3600,
        batch_size=10,
        refund_grace_seconds=0,
        rpc_client=rpc,
        session_factory=_session_factory,
    )
    await sweeper.sweep_once()

    await session.refresh(token)
    assert token.status == "refunded"
    assert token.tx_hash == "0xrefund_ipfs_rental_002"
    assert rpc.refunded == ["ipfs_rental_002"]
    assert rpc.released == []


async def test_sweeper_skips_active_not_yet_expired(session: AsyncSession) -> None:
    """A rental still in its term is left untouched."""
    now = datetime.now(UTC)
    token = IpfsRentalToken(
        access_key="ak_active",
        access_secret="secret",
        rental_id="ipfs_rental_003",
        offer_id="offer-3",
        cid="QmTest3",
        buyer_address="0xab0797Ae8cfF09B313c71cAb2f894B342b6e1d76",
        provider_address="0x241D3e44d42b6d4c270d0231780913f14386d90C",
        escrow_contract_id="ipfs_rental_003",
        pinned=True,
        status="active",
        created_at=now,
        expires_at=now + timedelta(days=1),
        updated_at=now,
    )
    session.add(token)
    await session.commit()

    rpc = FakeBlockchainRPCClient()
    sweeper = IpfsRentalSweeper(
        interval_seconds=3600,
        batch_size=10,
        refund_grace_seconds=0,
        rpc_client=rpc,
        session_factory=_session_factory,
    )
    await sweeper.sweep_once()

    await session.refresh(token)
    assert token.status == "active"
    assert token.tx_hash is None
    assert rpc.released == []
    assert rpc.refunded == []


async def test_425_lock_not_sealed_is_retried_by_next_sweep(monkeypatch) -> None:
    """Node answers 425 ('lock not sealed yet') once, then 200.

    The token must be marked expired immediately (access keys stop) but stay
    inside the sweep's retry set until the escrow actually settles -- an
    'expired' token with no tx_hash is an unsettled escrow, not a settled one.
    Uses the real BlockchainRPCClient over httpx.MockTransport so raise_for_status
    behaviour is exercised, not stubbed.
    """
    now = datetime.now(UTC)
    async with _session_factory() as session:
        token = IpfsRentalToken(
            access_key="ak_t67_425",
            access_secret="secret",
            rental_id="ipfs_rental_425",
            offer_id="offer-425",
            cid="QmTest425",
            buyer_address="0xab0797ae8cff09b313c71cab2f894b342b6e1d76",
            provider_address="0x241d3e44d42b6d4c270d0231780913f14386d90c",
            escrow_contract_id="ipfs_rental_425",
            pinned=True,
            status="active",
            created_at=now - timedelta(days=2),
            expires_at=now - timedelta(hours=1),
            updated_at=now - timedelta(days=2),
        )
        session.add(token)
        await session.commit()

    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(
                425,
                json={"detail": "escrow lock is not sealed yet"},
                headers={"Retry-After": "5"},
                request=request,
            )
        return httpx.Response(200, json={"success": True, "tx_hash": "0xsealed"}, request=request)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)

    from aitbc.market import BlockchainRPCClient

    sweeper = IpfsRentalSweeper(
        interval_seconds=3600,
        batch_size=10,
        refund_grace_seconds=0,
        rpc_client=BlockchainRPCClient(rpc_url="http://node.invalid"),
        session_factory=_session_factory,
    )

    async def _token() -> IpfsRentalToken:
        async with _session_factory() as session:
            return await session.get(IpfsRentalToken, "ak_t67_425")

    await sweeper.sweep_once()
    token = await _token()
    assert token.status == "expired"  # access stops immediately — intended
    assert token.tx_hash is None

    await sweeper.sweep_once()
    token = await _token()
    assert token.status == "released"
    assert token.tx_hash == "0xsealed"
    assert state["calls"] == 2


class ScriptedRPC:
    """RPC client whose answers are scripted per job_id (falsy = 'not yet')."""

    def __init__(
        self,
        fail_release: set[str] | None = None,
        fail_refund: set[str] | None = None,
        missing: set[str] | None = None,
    ) -> None:
        self.released: list[str] = []
        self.refunded: list[str] = []
        self.fail_release = fail_release or set()
        self.fail_refund = fail_refund or set()
        self.missing = missing or set()

    async def release_escrow(self, job_id: str) -> dict[str, Any] | None:
        self.released.append(job_id)
        if job_id in self.fail_release:
            return {"success": False, "message": "could not be settled on-chain"}
        return {"success": True, "tx_hash": f"0xrelease_{job_id}"}

    async def refund_escrow(self, job_id: str) -> dict[str, Any] | None:
        self.refunded.append(job_id)
        if job_id in self.fail_refund:
            return {"success": False, "message": "could not be settled on-chain"}
        return {"success": True, "tx_hash": f"0xrefund_{job_id}"}

    async def verify_escrow(self, job_id: str) -> dict[str, Any] | None:
        if job_id in self.missing:
            return None
        return {"job_id": job_id, "status": "locked"}


def _expired_token(access_key: str, rental_id: str, **overrides) -> IpfsRentalToken:
    now = datetime.now(UTC)
    data: dict[str, Any] = {
        "access_key": access_key,
        "access_secret": "secret",
        "rental_id": rental_id,
        "offer_id": f"offer-{access_key}",
        "cid": f"Qm{access_key}",
        "buyer_address": "0xab0797ae8cff09b313c71cab2f894b342b6e1d76",
        "provider_address": "0x241d3e44d42b6d4c270d0231780913f14386d90c",
        "escrow_contract_id": rental_id,
        "pinned": True,
        "status": "expired",
        "created_at": now - timedelta(days=2),
        "expires_at": now - timedelta(hours=1),
        "updated_at": now - timedelta(days=2),
    }
    data.update(overrides)
    return IpfsRentalToken(**data)


async def test_failed_settle_stamps_the_deferral_marker() -> None:
    """A settle answer that is not success defers: the token stays 'expired'
    and stamps settle_deferral_first_at instead of looping unmarked."""
    async with _session_factory() as session:
        session.add(_expired_token("ak_defer1", "r_defer1"))
        await session.commit()

    rpc = ScriptedRPC(fail_release={"r_defer1"})
    sweeper = IpfsRentalSweeper(batch_size=10, refund_grace_seconds=0, rpc_client=rpc, session_factory=_session_factory)
    await sweeper.sweep_once()

    async with _session_factory() as session:
        token = await session.get(IpfsRentalToken, "ak_defer1")
        assert token is not None
        assert token.status == "expired"
        assert token.tx_hash is None
        assert token.settle_deferral_first_at is not None


async def test_deferral_past_bound_goes_terminal() -> None:
    """A token whose deferral exceeds the bound leaves the sweep set as
    settlement_failed instead of looping every interval forever."""
    first_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=7)
    async with _session_factory() as session:
        session.add(_expired_token("ak_terminal", "r_terminal", settle_deferral_first_at=first_at))
        await session.commit()

    rpc = ScriptedRPC(fail_release={"r_terminal"})
    sweeper = IpfsRentalSweeper(batch_size=10, refund_grace_seconds=0, rpc_client=rpc, session_factory=_session_factory)
    await sweeper.sweep_once()

    async with _session_factory() as session:
        token = await session.get(IpfsRentalToken, "ak_terminal")
        assert token is not None
        assert token.status == "settlement_failed"
        assert token.settle_deferral_first_at is None


async def test_phantom_escrow_goes_terminal_before_the_bound() -> None:
    """A job_id the chain has no escrow row for can never settle: after the
    first deferral a still-absent verify_escrow probe must mark
    settlement_failed immediately, not at the settle_max_seconds bound."""
    first_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
    async with _session_factory() as session:
        session.add(_expired_token("ak_phantom", "r_phantom", settle_deferral_first_at=first_at))
        await session.commit()

    rpc = ScriptedRPC(fail_release={"r_phantom"}, missing={"r_phantom"})
    sweeper = IpfsRentalSweeper(batch_size=10, refund_grace_seconds=0, rpc_client=rpc, session_factory=_session_factory)
    await sweeper.sweep_once()

    async with _session_factory() as session:
        token = await session.get(IpfsRentalToken, "ak_phantom")
        assert token is not None
        assert token.status == "settlement_failed"
        assert token.settle_deferral_first_at is None


async def test_present_escrow_still_defers_until_the_bound() -> None:
    """A settle failure whose escrow row exists stays in the retry set: the
    absent-row fast path must not kill rows the chain still knows about."""
    first_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)
    async with _session_factory() as session:
        session.add(_expired_token("ak_present", "r_present", settle_deferral_first_at=first_at))
        await session.commit()

    rpc = ScriptedRPC(fail_release={"r_present"})
    sweeper = IpfsRentalSweeper(batch_size=10, refund_grace_seconds=0, rpc_client=rpc, session_factory=_session_factory)
    await sweeper.sweep_once()

    async with _session_factory() as session:
        token = await session.get(IpfsRentalToken, "ak_present")
        assert token is not None
        assert token.status == "expired"
        assert token.settle_deferral_first_at is not None


async def test_successful_settle_clears_the_deferral_marker() -> None:
    first_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    async with _session_factory() as session:
        session.add(_expired_token("ak_clear", "r_clear", settle_deferral_first_at=first_at))
        await session.commit()

    rpc = ScriptedRPC()
    sweeper = IpfsRentalSweeper(batch_size=10, refund_grace_seconds=0, rpc_client=rpc, session_factory=_session_factory)
    await sweeper.sweep_once()

    async with _session_factory() as session:
        token = await session.get(IpfsRentalToken, "ak_clear")
        assert token is not None
        assert token.status == "released"
        assert token.settle_deferral_first_at is None


async def test_stuck_rows_cannot_starve_an_eligible_row() -> None:
    """More stuck rows than the batch limit must not starve an eligible one:
    least-recently-processed-first ordering plus the updated_at bump rotates
    stuck rows to the back of the queue."""
    now = datetime.now(UTC)
    first_at = now.replace(tzinfo=None) - timedelta(hours=1)
    stuck_ids = [f"r_stuck{i}" for i in range(50)]
    async with _session_factory() as session:
        for i, rid in enumerate(stuck_ids):
            session.add(
                _expired_token(
                    f"ak_stuck{i}",
                    rid,
                    settle_deferral_first_at=first_at,
                    updated_at=now - timedelta(hours=2),
                )
            )
        # Newer updated_at than the stuck set: strictly behind them on the
        # first pass, strictly ahead once they rotate.
        session.add(_expired_token("ak_eligible", "r_eligible", updated_at=now - timedelta(hours=1)))
        await session.commit()

    rpc = ScriptedRPC(fail_release=set(stuck_ids))
    sweeper = IpfsRentalSweeper(batch_size=50, refund_grace_seconds=0, rpc_client=rpc, session_factory=_session_factory)

    await sweeper.sweep_once()
    assert "r_eligible" not in rpc.released

    await sweeper.sweep_once()
    assert "r_eligible" in rpc.released

    async with _session_factory() as session:
        token = await session.get(IpfsRentalToken, "ak_eligible")
        assert token is not None
        assert token.status == "released"
        assert token.tx_hash == "0xrelease_r_eligible"
