"""Unit tests for aitbc.wallet shared types (v0.12.0 §A1).

Covers agent wallet balances/transfers, escrow lifecycle, and allowance
spending.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from aitbc.wallet import (
    AgentWallet,
    AllowanceExceededError,
    Escrow,
    EscrowAllowance,
    EscrowError,
    EscrowStatus,
    InsufficientBalanceError,
    WalletStatus,
)


def test_agent_wallet_deposit_and_withdraw() -> None:
    wallet = AgentWallet(
        wallet_id="w1",
        agent_id="agent-a",
        chain_id="ait-hub",
    )
    wallet.deposit("AITBC", Decimal("100"))
    assert wallet.balance("AITBC") == Decimal("100")

    wallet.withdraw("AITBC", Decimal("30"))
    assert wallet.balance("AITBC") == Decimal("70")


def test_agent_wallet_transfer() -> None:
    a = AgentWallet(wallet_id="w1", agent_id="agent-a", chain_id="ait-hub")
    b = AgentWallet(wallet_id="w2", agent_id="agent-b", chain_id="ait-hub")
    a.deposit("AITBC", Decimal("100"))
    a.transfer("AITBC", Decimal("40"), b)
    assert a.balance("AITBC") == Decimal("60")
    assert b.balance("AITBC") == Decimal("40")


def test_agent_wallet_insufficient_balance() -> None:
    wallet = AgentWallet(wallet_id="w1", agent_id="agent-a", chain_id="ait-hub")
    wallet.deposit("AITBC", Decimal("10"))
    with pytest.raises(InsufficientBalanceError):
        wallet.withdraw("AITBC", Decimal("11"))


def test_agent_wallet_frozen_withdraw() -> None:
    wallet = AgentWallet(
        wallet_id="w1",
        agent_id="agent-a",
        chain_id="ait-hub",
        status=WalletStatus.FROZEN,
    )
    wallet.deposit("AITBC", Decimal("100"))
    with pytest.raises(ValueError):
        wallet.withdraw("AITBC", Decimal("10"))


def test_escrow_release() -> None:
    escrow = Escrow(
        escrow_id="e1",
        payer_id="agent-a",
        payee_id="agent-b",
        token="AITBC",
        amount=Decimal("50"),
    )
    escrow.release()
    assert escrow.status == EscrowStatus.RELEASED


def test_escrow_refund_after_release_fails() -> None:
    escrow = Escrow(
        escrow_id="e1",
        payer_id="agent-a",
        payee_id="agent-b",
        token="AITBC",
        amount=Decimal("50"),
    )
    escrow.release()
    with pytest.raises(EscrowError):
        escrow.refund()


def test_escrow_expired() -> None:
    now = datetime.now(UTC)
    escrow = Escrow(
        escrow_id="e1",
        payer_id="agent-a",
        payee_id="agent-b",
        token="AITBC",
        amount=Decimal("50"),
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    assert escrow.is_expired(now) is True


def test_escrow_negative_amount() -> None:
    with pytest.raises(ValueError):
        Escrow(
            escrow_id="e1",
            payer_id="agent-a",
            payee_id="agent-b",
            token="AITBC",
            amount=Decimal("-1"),
        )


def test_allowance_spend() -> None:
    allowance = EscrowAllowance(
        allowance_id="a1",
        owner_id="agent-a",
        spender_id="agent-b",
        token="AITBC",
        amount=Decimal("100"),
    )
    allowance.spend(Decimal("30"))
    assert allowance.remaining == Decimal("70")
    assert allowance.used == Decimal("30")


def test_allowance_exceeded() -> None:
    allowance = EscrowAllowance(
        allowance_id="a1",
        owner_id="agent-a",
        spender_id="agent-b",
        token="AITBC",
        amount=Decimal("100"),
    )
    allowance.spend(Decimal("60"))
    with pytest.raises(AllowanceExceededError):
        allowance.spend(Decimal("50"))


def test_allowance_used_exceeds_amount() -> None:
    with pytest.raises(ValueError):
        EscrowAllowance(
            allowance_id="a1",
            owner_id="agent-a",
            spender_id="agent-b",
            token="AITBC",
            amount=Decimal("100"),
            used=Decimal("101"),
        )
