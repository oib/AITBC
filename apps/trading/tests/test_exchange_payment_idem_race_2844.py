"""#2844: ExchangePayment idempotency race — a same-key request that loses
the check-then-insert race must replay the winner's stored row, not 500.

The route is exercised directly with a session double: the pre-check
``scalar`` misses (the race window), ``commit`` raises the UNIQUE
IntegrityError, and the post-rollback re-read returns the winner.
"""

from decimal import Decimal

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from trading_service.domain.exchange_payment import ExchangePayment
from trading_service.routers.exchange_compat import (
    ETHEREUM_CONFIG,
    ExchangePaymentRequest,
    create_exchange_payment,
)


def _request(key: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/exchange/create-payment",
            "headers": [(b"idempotency-key", key.encode())],
        }
    )


def _payment_request(user_id: str = "user-a") -> ExchangePaymentRequest:
    ait = Decimal("50")
    return ExchangePaymentRequest(
        user_id=user_id,
        aitbc_amount=ait,
        eth_amount=ait / ETHEREUM_CONFIG["exchange_rate"],
    )


def _winner(user_id: str = "user-a") -> ExchangePayment:
    return ExchangePayment(
        payment_id="ex_winner00000001",
        user_id=user_id,
        aitbc_amount=Decimal("50"),
        eth_amount=Decimal("50") / ETHEREUM_CONFIG["exchange_rate"],
        payment_address="0x0000000000000000000000000000000000000000",
        status="pending",
        idempotency_key="k-race",
        created_at=1,
        expires_at=9999999999,
        confirmations=0,
    )


class _RacingSession:
    """First scalar (pre-check) misses; commit loses the UNIQUE race; the
    post-rollback scalar returns the winner's row."""

    def __init__(self, winner):
        self._winner = winner
        self._scalar_calls = 0
        self.rollbacks = 0

    async def scalar(self, _stmt):
        self._scalar_calls += 1
        return None if self._scalar_calls == 1 else self._winner

    def add(self, _row):
        pass

    async def commit(self):
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed: exchange_payment.idempotency_key"))

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, _row):
        pass


async def test_lost_idempotency_race_replays_winner():
    session = _RacingSession(_winner())
    result = await create_exchange_payment(
        _payment_request(),
        BackgroundTasks(),
        _request("k-race"),
        session,  # type: ignore[arg-type]
    )
    assert result["payment_id"] == "ex_winner00000001"
    assert result["user_id"] == "user-a"
    assert session.rollbacks == 1


async def test_lost_idempotency_race_other_user_is_409():
    session = _RacingSession(_winner(user_id="user-b"))
    with pytest.raises(HTTPException) as exc:
        await create_exchange_payment(
            _payment_request("user-a"),
            BackgroundTasks(),
            _request("k-race"),
            session,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == 409
    assert session.rollbacks == 1
