"""``expires_at`` is enforced, and ``/register`` decides atomically (#1579, #1580).

``CoinRequest.expires_at`` is written as ``created_at + REQUEST_TTL`` (24h) and
described as "how long a registered request stays executable" — but nothing
used to read it: ``/execute`` paid an approved request forever, the sweeper only
touched pending rows after 30 days, and an approved grant past its TTL still
counted as a prior grant. These tests pin the enforcement at decision time,
spend time and sweep time.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import FastAPI

from aitbc.db import get_db_session
from aitbc.models import CoinRequest, CoinRequestStatus

from agent_app.lifespan import sweep_expired_coin_requests
from agent_app.routers import coin_requests as coin_requests_router

from .conftest import API_KEY, PAYOUT, signed_transactions, stored_request

WALLET = "0xf3290d4F0D96a2Dd231C44362c57d5ad0AF0A281"


def _register(client, key: str | None = API_KEY, **overrides):
    body = {
        "request_id": "req-0001",
        "sender": "agent-alpha",
        "amount": PAYOUT,
        "wallet_address": WALLET,
    }
    body.update(overrides)
    headers = {"x-api-key": key} if key is not None else {}
    return client.post("/api/v1/agent/coin-requests/register", json=body, headers=headers)


def _execute(client, request_id: str = "req-0001", key: str | None = API_KEY, **overrides):
    body = {"request_id": request_id, "sender": "agent-alpha", "amount": PAYOUT, "wallet_address": WALLET}
    body.update(overrides)
    headers = {"x-api-key": key} if key is not None else {}
    return client.post("/api/v1/agent/coin-requests/execute", json=body, headers=headers)


def _expire(request_id: str) -> None:
    """Push a stored request's expires_at into the past, keeping its status."""
    with get_db_session() as session:
        row = session.query(CoinRequest).filter(CoinRequest.id == request_id).first()
        assert row is not None
        row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)


def _add_request(request_id: str, status: CoinRequestStatus, *, expires_at, sender="agent-x", tx_hash=None) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    with get_db_session() as session:
        session.add(
            CoinRequest(
                id=request_id,
                sender=sender,
                recipient="hub-coordinator",
                amount=PAYOUT,
                wallet_address=WALLET,
                status=status,
                approval_mode="manual",
                created_at=now - timedelta(days=2),
                expires_at=expires_at,
                transaction_hash=tx_hash,
            )
        )


# --- Spend time -------------------------------------------------------------------------


def test_an_approved_request_past_expires_at_cannot_be_executed(bare_client) -> None:
    assert _register(bare_client).json()["status"] == "approved"
    _expire("req-0001")

    response = _execute(bare_client)

    assert response.status_code == 409
    assert "expired" in response.json()["detail"]
    stored = stored_request("req-0001")
    assert stored is not None
    assert stored.status == CoinRequestStatus.EXPIRED
    assert signed_transactions() == []


def test_an_approved_request_within_expires_at_still_executes(bare_client) -> None:
    assert _register(bare_client).json()["status"] == "approved"

    assert _execute(bare_client).status_code == 200
    assert len(signed_transactions()) == 1


def test_a_paid_request_past_expires_at_still_replays_its_hash(bare_client) -> None:
    """Expiry must not strand reconciliation: a settled payment reports its tx."""
    assert _register(bare_client).json()["status"] == "approved"
    assert _execute(bare_client).status_code == 200
    _expire("req-0001")

    response = _execute(bare_client)

    assert response.status_code == 200
    assert response.json()["already_executed"] is True


# --- Sweep time -------------------------------------------------------------------------


def test_the_sweeper_expires_pending_and_unexecuted_approved_rows(bare_client) -> None:
    past = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    future = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
    _add_request("pend-old", CoinRequestStatus.PENDING, expires_at=past)
    _add_request("appr-old", CoinRequestStatus.APPROVED, expires_at=past)
    _add_request("appr-paid", CoinRequestStatus.APPROVED, expires_at=past, tx_hash="0x" + "ab" * 32)
    _add_request("pend-fresh", CoinRequestStatus.PENDING, expires_at=future)

    with get_db_session() as session:
        expired = sweep_expired_coin_requests(session)

    assert expired == 2
    assert stored_request("pend-old").status == CoinRequestStatus.EXPIRED
    assert stored_request("appr-old").status == CoinRequestStatus.EXPIRED
    # A paid grant keeps its APPROVED record — expiry never rewrites a payment.
    assert stored_request("appr-paid").status == CoinRequestStatus.APPROVED
    assert stored_request("pend-fresh").status == CoinRequestStatus.PENDING


# --- Decision time ----------------------------------------------------------------------


def test_an_expired_grant_does_not_block_a_fresh_registration(bare_client) -> None:
    """A grant that lapsed unexecuted can never be spent, so it is not a prior grant."""
    assert _register(bare_client).json()["status"] == "approved"
    _expire("req-0001")

    second = _register(bare_client, request_id="req-0002")

    assert second.json()["status"] == "approved"


def test_a_live_grant_still_blocks_a_second_registration(bare_client) -> None:
    assert _register(bare_client).json()["status"] == "approved"

    assert _register(bare_client, request_id="req-0002").json()["status"] == "pending"


# --- Register atomicity and idempotency -------------------------------------------------


async def test_concurrent_registrations_for_one_wallet_approve_exactly_once(coin_request_env) -> None:
    """Two racing first-grants to the same destination: one wins, one parks (#1580).

    The decide+insert runs under BEGIN IMMEDIATE, so the loser's prior-grant
    probe sees the winner's committed row instead of both passing on an empty
    table. ASGITransport + asyncio.gather gives real concurrency — the sync
    endpoint runs in the threadpool.
    """
    app = FastAPI()
    app.include_router(coin_requests_router.router)

    async def post(request_id: str) -> dict:
        body = {
            "request_id": request_id,
            "sender": f"agent-{request_id}",
            "amount": PAYOUT,
            "wallet_address": WALLET,
        }
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/agent/coin-requests/register", json=body, headers={"x-api-key": API_KEY})
        assert response.status_code == 200
        return response.json()

    results = await asyncio.gather(post("req-race-a"), post("req-race-b"))

    assert sorted(r["status"] for r in results) == ["approved", "pending"]


def test_re_registering_the_same_id_with_a_different_sender_is_refused(bare_client) -> None:
    """Idempotent replay must not silently accept a different caller's terms (#1579)."""
    assert _register(bare_client).json()["status"] == "approved"

    response = _register(bare_client, sender="agent-beta")

    assert response.status_code == 409
