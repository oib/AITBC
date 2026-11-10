"""Concurrency pin for POST /v1/escrow/release (ESCROW-RELEASE-1 follow-on).

The relay dedups on ``job_id``: SELECT the stored row, else POST the release
to the settlement node and INSERT the relay row — with ``job_id`` UNIQUE as
the backstop (``_insert_or_existing`` converts the loser's IntegrityError
into a replay of the stored result). Two simultaneous releases can still
both pass the SELECT before either INSERTs, so both may POST to the chain;
the persistence-layer guard must still leave exactly one relay row and two
successful responses, with the chain's own state check as the final
arbiter of the duplicate POST.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlmodel import Session, SQLModel

from coordinator_api.contexts.payments.domain.escrow_release_relay import EscrowReleaseRelay
from coordinator_api.contexts.payments.services.escrow_release_relay import EscrowReleaseRelayService

PATCH_TARGET = "coordinator_api.contexts.payments.services.escrow_release_relay.AsyncAITBCHTTPClient"

_ESCROW = {
    "job_id": "mkt_conc_1",
    "contract_id": "0xc1",
    "state": "funded",
    "buyer": "0x08aB801150eF3496344cFA78fe025c3B48Caf435",
    "provider": "0xF4924759508E420eeD947BD33326731B11c4B7Df",
    "amount": "2.0",
    "released_at": None,
    "refunded_at": None,
    "release_tx_hash": None,
}


@pytest.fixture
def release_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'escrow_conc.db'}")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _chain_client_mock() -> AsyncMock:
    client = AsyncMock()
    client.get.return_value = dict(_ESCROW)
    client.post.return_value = {"success": True, "tx_hash": "0xrel1", "contract_id": "0xc1"}
    return client


@pytest.mark.asyncio
async def test_concurrent_releases_leave_single_relay_row(release_engine) -> None:
    mock_client = _chain_client_mock()
    body = {"job_id": "mkt_conc_1", "amount": "1.5", "job_tx_hash": "0xjobtx"}

    with patch(PATCH_TARGET, return_value=mock_client):
        s1, s2 = Session(release_engine), Session(release_engine)
        try:
            results = await asyncio.gather(
                EscrowReleaseRelayService(s1).release("admin-1", True, dict(body)),
                EscrowReleaseRelayService(s2).release("admin-1", True, dict(body)),
                return_exceptions=True,
            )
        finally:
            s1.close()
            s2.close()

    assert not any(isinstance(r, BaseException) for r in results), f"release raised: {results!r}"
    assert all(r.get("success") for r in results), f"unexpected results: {results!r}"

    with Session(release_engine) as check:
        rows = check.execute(select(EscrowReleaseRelay).where(EscrowReleaseRelay.job_id == "mkt_conc_1")).scalars().all()
    assert len(rows) == 1, f"expected exactly one relay row, got {len(rows)}"

    # The dedup SELECT runs before the INSERT on both callers, so a wider
    # interleaving could still emit a second chain POST — the stored row
    # wins either way and the chain's own already-released check is the
    # backstop. Observed here: full serialization (1 POST); pin the bound so
    # a regression that lets the loser surface a 500 fails loudly.
    assert 1 <= mock_client.post.call_count <= 2
