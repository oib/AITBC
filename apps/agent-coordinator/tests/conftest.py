"""Shared fixtures for the coin-request faucet tests (V23-62).

The faucet is the one path in the tree that moves money without a signature from the payer,
so its tests need two things held constant: a signer that cannot actually emit a transaction,
and a database that is not the deployed one.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

pytest.importorskip("fastapi", reason="agent-coordinator app dependencies not installed")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aitbc.db import agent_db  # noqa: E402
from aitbc.models import CoinRequest, CoinRequestStatus  # noqa: E402
from agent_app.routers import coin_requests  # noqa: E402

API_KEY = "test-coordinator-api-key"
TREASURY_BALANCE = 3_600_000_000_000
TX_HASH = "0x" + "cd" * 32

# Under the hub's automatic ceiling of 360000, so the faucet policy approves it unattended.
PAYOUT = 100


class FakeTransactionService:
    """Stands in for the real signer so no test can emit a transaction."""

    instances: list[FakeTransactionService] = []

    def __init__(self) -> None:
        self.genesis_private_key = "0x" + "11" * 32
        self.genesis_address = "0xF5A930bBC90c15dB0bbf28f8485D18eEf24c3F43"
        self.rpc_url = "http://localhost:8202"
        self.signed: list[dict] = []
        FakeTransactionService.instances.append(self)

    def get_balance(self, _address: str) -> int:
        return TREASURY_BALANCE

    def generate_signed_transaction(self, to_address: str, amount: int, fee: int) -> dict:
        payload = {"to": to_address, "amount": amount, "fee": fee}
        self.signed.append(payload)
        return payload


class FakeHttpClient:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def post(self, _path: str, json: dict) -> dict:  # noqa: A002
        return {"transaction_hash": TX_HASH}


def signed_transactions() -> list[dict]:
    """Every transaction any service instance signed during this test."""
    return [tx for service in FakeTransactionService.instances for tx in service.signed]


def stored_request(request_id: str) -> CoinRequest | None:
    """Read a request back out of the test database, detached from its session."""
    with agent_db.get_db_session() as session:
        found = session.query(CoinRequest).filter(CoinRequest.id == request_id).first()
        if found is not None:
            session.expunge(found)
        return found


def store_request(session, spec: dict, status: CoinRequestStatus, sender: str = "agent-under-test") -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    session.add(
        CoinRequest(
            id=spec["id"],
            sender=sender,
            recipient=spec["wallet_address"],
            amount=spec["amount"],
            wallet_address=spec["wallet_address"],
            status=status,
            approval_mode="manual",
            approved_by="cli" if status is CoinRequestStatus.APPROVED else None,
            created_at=now,
            expires_at=now + timedelta(days=1),
        )
    )


@pytest.fixture
def faucet_env(monkeypatch, tmp_path):
    """A hub with a real (empty) database, a fake signer and a known API key."""
    FakeTransactionService.instances.clear()
    monkeypatch.setenv("COORDINATOR_API_KEY", API_KEY)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("FAUCET_AUTO_APPROVE_MAX", raising=False)
    monkeypatch.setattr(coin_requests, "TransactionService", FakeTransactionService)
    monkeypatch.setattr("aitbc.network.AITBCHTTPClient", FakeHttpClient, raising=False)

    # The engine is a module global cached on first use, so pointing AGENT_DB_PATH at a
    # fresh file is not enough on its own.
    monkeypatch.setenv("AGENT_DB_PATH", str(tmp_path / "coin_requests.db"))
    monkeypatch.setattr(agent_db, "_engine", None)
    monkeypatch.setattr(agent_db, "_SessionLocal", None)
    agent_db.init_db()

    yield

    agent_db._engine = None
    agent_db._SessionLocal = None


@pytest.fixture
def bare_client(faucet_env):
    """A hub whose database has no requests in it at all."""
    app = FastAPI()
    app.include_router(coin_requests.router)
    return TestClient(app)
