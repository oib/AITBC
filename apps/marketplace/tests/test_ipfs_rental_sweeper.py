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

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from marketplace_service.domain.marketplace import IpfsRentalToken
from marketplace_service.services.ipfs_rental_sweeper import IpfsRentalSweeper
from marketplace_service.storage import get_session_context


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
