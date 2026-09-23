"""Regression tests: GPU_MARKET must never carry value.

The /rpc/transactions/market endpoint exempts ``offer``/``software_offer``
payloads from signature verification (the market CLI has no wallet keys).
The exemption rested on offers being value-zero listings, but nothing enforced
it: consensus has no GPU_MARKET branch, so a nonzero amount fell through
to the generic transfer and debited ``from`` — any address the caller named —
with no signature anywhere in the path.

Covers both layers of the fix:
  * route level — unsigned offers with a nonzero amount are rejected outright;
  * consensus level — validate_transaction and compute_state_delta both refuse
    a nonzero-value GPU_MARKET regardless of how it arrived.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlmodel import Session

from aitbc_chain.base_models import _to_ait_address
from aitbc_chain.metadata import chain_metadata
from aitbc_chain.rpc import transactions as tx_mod
from aitbc_chain.state.pure_state_transition import compute_state_delta
from aitbc_chain.state.state_transition import StateTransition

VICTIM = _to_ait_address("0x0000000000000000000000000000000000000bad")
ATTACKER = _to_ait_address("0x0000000000000000000000000000000000000eef")


def _offer_tx(amount: int, action: str = "software_offer") -> dict[str, Any]:
    return {
        "from": VICTIM,
        "to": ATTACKER,
        "amount": amount,
        "fee": 0,
        "nonce": 0,
        "type": "GPU_MARKET",
        "payload": {"action": action, "service_type": "whisper", "price_per_unit": 0},
        "chain_id": "test",
    }


# ---------------------------------------------------------------------------
# Route level — the unsigned offer exemption must not carry value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["offer", "software_offer"])
async def test_unsigned_offer_with_amount_rejected(action: str):
    """An unsigned offer carrying amount>0 must be refused before mempool."""
    with pytest.raises(HTTPException) as exc_info:
        await tx_mod.submit_market_transaction(MagicMock(), _offer_tx(10**9, action))
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_unsigned_zero_amount_offer_still_admitted():
    """Zero-amount software offers keep working without a signature (V23-90)."""
    account = MagicMock()
    account.balance = 10**9
    account.nonce = 0

    @contextmanager
    def fake_session_scope(*_a, **_kw):
        session = MagicMock()
        session.get = MagicMock(return_value=account)
        yield session

    mempool = MagicMock()
    mempool.add = MagicMock(return_value="0xtxhash")

    with (
        patch.object(tx_mod, "session_scope", fake_session_scope),
        patch("aitbc_chain.mempool.get_mempool", return_value=mempool),
    ):
        result = await tx_mod.submit_market_transaction(MagicMock(), _offer_tx(0))
    assert result["success"] is True


# ---------------------------------------------------------------------------
# Consensus level — even if a nonzero-value tx reaches a block, it is invalid
# ---------------------------------------------------------------------------


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    chain_metadata.create_all(engine)
    from datetime import UTC, datetime

    now = datetime.now(UTC).isoformat()
    with Session(engine) as session:
        session.execute(
            text(
                "INSERT INTO account (chain_id, address, balance, nonce, updated_at) "
                "VALUES (:chain_id, :addr, :balance, 0, :now)"
            ),
            {"chain_id": "test", "addr": VICTIM, "balance": 10**9, "now": now},
        )
        session.commit()
    yield engine
    engine.dispose()


def test_validate_transaction_rejects_nonzero_market(engine):
    st = StateTransition()
    tx = _offer_tx(10**9)
    tx["value"] = tx["amount"]
    with Session(engine) as session:
        ok, msg = st.validate_transaction(session, "test", tx, "0xhash-nonzero")
    assert ok is False
    assert "value=0" in msg


def test_validate_transaction_accepts_zero_value_market(engine):
    st = StateTransition()
    tx = _offer_tx(0)
    tx["value"] = 0
    with Session(engine) as session:
        ok, msg = st.validate_transaction(session, "test", tx, "0xhash-zero")
    assert ok is True, msg


def test_pure_state_transition_rejects_nonzero_market():
    sender_account = MagicMock()
    sender_account.balance = 10**9
    sender_account.nonce = 0
    delta = compute_state_delta(
        {VICTIM: sender_account},
        {**_offer_tx(10**9), "value": 10**9},
        "test",
        tx_hash="0xhash-pure",
    )
    assert delta.success is False
    assert "value=0" in (delta.error or "")
