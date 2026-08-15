"""Regression tests for the stake lock-period calculation.

`stake_tokens` used to compute the unlock time as::

    locked_until.replace(day=locked_until.day + lock_days)

`datetime.replace(day=...)` rejects any day past the end of the month, so staking raised
`ValueError: day is out of range for month` on most days of the month -- after the staker's
balance had already been debited. These tests pin the arithmetic across month, year, and
leap-day boundaries so the endpoint cannot regress to calendar-unaware date math.
"""

from __future__ import annotations

import datetime as real_datetime
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from aitbc_chain.models import Account, Stake
from aitbc_chain.rpc import staking as staking_module
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

STAKER = "0x1111111111111111111111111111111111111111"


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'staking.db'}", echo=False)
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def staking_env(engine, monkeypatch):
    """Patch staking's collaborators so stake_tokens runs against the test DB.

    Signature verification and chain-id validation are stubbed out -- they have their own
    tests; these cases are only about the lock-period arithmetic.
    """

    @contextmanager
    def _session_scope():
        with Session(engine) as session:
            yield session

    monkeypatch.setattr(staking_module, "session_scope", _session_scope)
    monkeypatch.setattr(staking_module, "verify_request_signature", lambda *a, **kw: True)
    monkeypatch.setattr(staking_module, "validate_chain_id", lambda chain_id: True)
    monkeypatch.setattr(staking_module, "get_chain_id", lambda chain_id: chain_id or "ait-testnet")

    with Session(engine) as session:
        session.add(Account(chain_id="ait-testnet", address=STAKER, balance=1_000_000, nonce=0))
        session.commit()

    return engine


def _freeze_now(monkeypatch, frozen: datetime) -> None:
    """Freeze `datetime.now` inside the staking module only."""

    class _FrozenDatetime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return frozen if tz is None else frozen.astimezone(tz)

    monkeypatch.setattr(staking_module, "datetime", _FrozenDatetime)


async def _stake(amount: int = 1000, lock_days: int = 30) -> dict:
    return await staking_module.stake_tokens(
        request=None,
        stake_data={
            "address": STAKER,
            "amount": amount,
            "chain_id": "ait-testnet",
            "lock_days": lock_days,
            "signature": "0x" + "ab" * 65,
        },
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "frozen",
    [
        pytest.param(datetime(2026, 1, 31, 12, 0, tzinfo=UTC), id="month-end-31st"),
        pytest.param(datetime(2026, 1, 15, 12, 0, tzinfo=UTC), id="mid-month"),
        pytest.param(datetime(2026, 2, 28, 12, 0, tzinfo=UTC), id="short-month-end"),
        pytest.param(datetime(2024, 2, 29, 12, 0, tzinfo=UTC), id="leap-day"),
        pytest.param(datetime(2026, 12, 20, 12, 0, tzinfo=UTC), id="year-boundary"),
        pytest.param(datetime(2026, 4, 30, 12, 0, tzinfo=UTC), id="30-day-month-end"),
    ],
)
async def test_stake_succeeds_on_any_calendar_day(staking_env, monkeypatch, frozen: datetime) -> None:
    """Staking must succeed regardless of the day of month it is invoked on."""
    _freeze_now(monkeypatch, frozen)

    result = await _stake(lock_days=30)

    assert result["success"] is True
    assert datetime.fromisoformat(result["locked_until"]) == frozen + timedelta(days=30)


@pytest.mark.anyio
async def test_balance_is_debited_exactly_once(staking_env, monkeypatch) -> None:
    """The balance debit and the Stake row must both land -- the old bug raised between them."""
    _freeze_now(monkeypatch, datetime(2026, 1, 31, 12, 0, tzinfo=UTC))

    result = await _stake(amount=1000, lock_days=30)

    with Session(staking_env) as session:
        account = session.get(Account, ("ait-testnet", STAKER))
        stakes = session.exec(select(Stake).where(Stake.address == STAKER)).all()

    assert account is not None
    assert account.balance == 1_000_000 - 1000
    assert result["remaining_balance"] == 1_000_000 - 1000
    assert len(stakes) == 1
    assert stakes[0].amount == 1000


@pytest.mark.anyio
@pytest.mark.parametrize("lock_days", [1, 7, 365, 3650])
async def test_lock_period_honours_requested_duration(staking_env, monkeypatch, lock_days: int) -> None:
    frozen = datetime(2026, 1, 31, 12, 0, tzinfo=UTC)
    _freeze_now(monkeypatch, frozen)

    result = await _stake(lock_days=lock_days)

    assert datetime.fromisoformat(result["locked_until"]) == frozen + timedelta(days=lock_days)


@pytest.mark.anyio
@pytest.mark.parametrize("lock_days", [0, -1, 3651, 10**9])
async def test_out_of_range_lock_days_rejected(staking_env, monkeypatch, lock_days: int) -> None:
    """Absurd durations must be a 400, not an unhandled overflow."""
    _freeze_now(monkeypatch, datetime(2026, 1, 15, 12, 0, tzinfo=UTC))

    with pytest.raises(HTTPException) as exc:
        await _stake(lock_days=lock_days)

    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_insufficient_balance_leaves_account_untouched(staking_env, monkeypatch) -> None:
    _freeze_now(monkeypatch, datetime(2026, 1, 15, 12, 0, tzinfo=UTC))

    with pytest.raises(HTTPException) as exc:
        await _stake(amount=10_000_000)

    assert exc.value.status_code == 400

    with Session(staking_env) as session:
        account = session.get(Account, ("ait-testnet", STAKER))

    assert account is not None
    assert account.balance == 1_000_000
