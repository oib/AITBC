"""Tests for the AIT->ETH withdrawal monitor.

Covers:
- reserve guard in _release_eth_for_withdrawal
- successful ETH release updates the withdrawal record
- release failure with insufficient reserve
- _refund_withdrawal submits a BRIDGE_REFUND and updates the record
- refund failure marks the record failed
- _pending_eth_reserve sums pending/insufficient-reserve withdrawals
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from decimal import Decimal as _Decimal


def _assert_decimal_close(actual, expected, tol=_Decimal("1e-15")):
    assert abs(actual - expected) < tol, f"{actual} != {expected} (within {tol})"


from wallet_app.bridge.bridge_db import (
    init_db,
    insert_withdrawal,
    get_withdrawal_by_ait_tx_hash,
)

# Deterministic test key/address. Must be the bridge wallet in the environment.
TEST_ETH_PRIVATE_KEY = "0x" + "11" * 32
TEST_ETH_ADDRESS = "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A"


@pytest.fixture
def monitor_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Configure the environment for bridge_withdraw_monitor and patch DB path."""
    db_path = tmp_path / "bridge.db"
    monkeypatch.setenv("ETH_WALLET_ADDRESS", TEST_ETH_ADDRESS)
    monkeypatch.setenv("ETH_WALLET_PRIVATE_KEY", TEST_ETH_PRIVATE_KEY)
    monkeypatch.setenv("GENESIS_WALLET_ADDRESS", TEST_ETH_ADDRESS)
    monkeypatch.setenv("GENESIS_WALLET_PRIVATE_KEY", TEST_ETH_PRIVATE_KEY)
    monkeypatch.setenv("BRIDGE_ADMIN_PRIVATE_KEY", TEST_ETH_PRIVATE_KEY)
    monkeypatch.setenv("ETH_RPC_URL", "http://localhost:0")

    with patch("wallet_app.bridge.bridge_db.DB_PATH", str(db_path)):
        init_db()
        # Import after the DB path is patched; the module also reads env at import.
        from wallet_app.bridge import bridge_withdraw_monitor as monitor

        monkeypatch.setattr(monitor, "ETH_WALLET_ADDRESS", TEST_ETH_ADDRESS)
        monkeypatch.setattr(monitor, "ETH_WALLET_PRIVATE_KEY", TEST_ETH_PRIVATE_KEY)
        monkeypatch.setattr(monitor, "GENESIS_WALLET_ADDRESS", TEST_ETH_ADDRESS)
        monkeypatch.setattr(monitor, "GENESIS_WALLET_PRIVATE_KEY", TEST_ETH_PRIVATE_KEY)
        monkeypatch.setattr(monitor, "ETH_WITHDRAW_GAS", 100_000)
        yield monitor


@pytest.fixture
def seed_withdrawal(monitor_env, request):
    """Insert a withdrawal record and return its ait_tx_hash."""
    insert_withdrawal(
        ait_tx_hash="0xa" * 64,
        from_address="0x1111111111111111111111111111111111111111",
        eth_address="0x2222222222222222222222222222222222222222",
        amount_ait=Decimal("10"),
        fee_ait=Decimal("0.05"),
        net_ait=Decimal("9.95"),
        amount_eth=Decimal("0.001"),
    )
    return "0xa" * 64


class TestPendingEthReserve:
    """_pending_eth_reserve must allocate ETH for active withdrawal requests."""

    def test_pending_reserve_sums_active_withdrawals(self, monitor_env):
        insert_withdrawal(
            ait_tx_hash="0xa" * 64,
            from_address="0x1111111111111111111111111111111111111111",
            eth_address="0x2222222222222222222222222222222222222222",
            amount_ait=Decimal("1"),
            fee_ait=Decimal("0.005"),
            net_ait=Decimal("0.995"),
            amount_eth=Decimal("0.0001"),
        )
        insert_withdrawal(
            ait_tx_hash="0xb" * 64,
            from_address="0x3333333333333333333333333333333333333333",
            eth_address="0x4444444444444444444444444444444444444444",
            amount_ait=Decimal("2"),
            fee_ait=Decimal("0.01"),
            net_ait=Decimal("1.99"),
            amount_eth=Decimal("0.0002"),
            status="insufficient_reserve",
        )
        insert_withdrawal(
            ait_tx_hash="0xc" * 64,
            from_address="0x5555555555555555555555555555555555555555",
            eth_address="0x6666666666666666666666666666666666666666",
            amount_ait=Decimal("3"),
            fee_ait=Decimal("0.015"),
            net_ait=Decimal("2.985"),
            amount_eth=Decimal("0.0003"),
            status="completed",
        )

        reserve = monitor_env._pending_eth_reserve()
        _assert_decimal_close(reserve, Decimal("0.0003"))

    def test_pending_reserve_excludes_completed(self, monitor_env):
        insert_withdrawal(
            ait_tx_hash="0xa" * 64,
            from_address="0x1111111111111111111111111111111111111111",
            eth_address="0x2222222222222222222222222222222222222222",
            amount_ait=Decimal("1"),
            fee_ait=Decimal("0.005"),
            net_ait=Decimal("0.995"),
            amount_eth=Decimal("0.0001"),
            status="completed",
        )
        assert monitor_env._pending_eth_reserve() == Decimal("0")


class TestReleaseEthForWithdrawal:
    """_release_eth_for_withdrawal reserve guard and success path."""

    @pytest.mark.asyncio
    async def test_release_success_with_sufficient_reserve(self, monitor_env, seed_withdrawal, monkeypatch):
        # balance 0.1 ETH, gas price 1 gwei -> gas cost 0.0001 ETH
        async def _coro(value):
            return value

        monkeypatch.setattr(
            monitor_env,
            "_eth_balance",
            lambda address: asyncio.ensure_future(_coro(Decimal("0.1"))),
        )
        monkeypatch.setattr(
            monitor_env,
            "_eth_gas_price",
            lambda: asyncio.ensure_future(_coro(1_000_000_000)),
        )

        sent = []

        async def _send_eth(to_address: str, amount_eth: Decimal) -> str:
            sent.append((to_address, amount_eth))
            return "0xeth_release_tx"

        monkeypatch.setattr(monitor_env, "_send_eth", _send_eth)

        eth_tx_hash = await monitor_env._release_eth_for_withdrawal(
            withdrawal_id="withdrawal_abc",
            ait_tx_hash=seed_withdrawal,
            eth_address="0x2222222222222222222222222222222222222222",
            amount_eth=Decimal("0.001"),
        )

        assert eth_tx_hash == "0xeth_release_tx"
        assert sent == [("0x2222222222222222222222222222222222222222", Decimal("0.001"))]

        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "completed"
        assert record["eth_tx_hash"] == "0xeth_release_tx"

    @pytest.mark.asyncio
    async def test_release_fails_when_reserve_insufficient(self, monitor_env, seed_withdrawal, monkeypatch):
        # balance 0.00015 ETH, gas price 1 gwei -> required 0.0002 ETH
        async def _coro(value):
            return value

        monkeypatch.setattr(
            monitor_env,
            "_eth_balance",
            lambda address: asyncio.ensure_future(_coro(Decimal("0.00015"))),
        )
        monkeypatch.setattr(
            monitor_env,
            "_eth_gas_price",
            lambda: asyncio.ensure_future(_coro(1_000_000_000)),
        )

        with pytest.raises(RuntimeError, match="Insufficient ETH reserve"):
            await monitor_env._release_eth_for_withdrawal(
                withdrawal_id="withdrawal_abc",
                ait_tx_hash=seed_withdrawal,
                eth_address="0x2222222222222222222222222222222222222222",
                amount_eth=Decimal("0.001"),
            )

        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        # The release function currently raises before updating status; the caller
        # (process_withdrawal) is expected to retry and eventually mark failed.
        assert record["status"] == "pending"

    @pytest.mark.asyncio
    async def test_reserve_guard_accounts_for_pending_withdrawals(self, monitor_env, monkeypatch):
        # Create a large pending withdrawal consuming almost all available ETH.
        insert_withdrawal(
            ait_tx_hash="0xb" * 64,
            from_address="0x3333333333333333333333333333333333333333",
            eth_address="0x4444444444444444444444444444444444444444",
            amount_ait=Decimal("1"),
            fee_ait=Decimal("0.005"),
            net_ait=Decimal("0.995"),
            amount_eth=Decimal("0.0095"),
        )

        async def _coro(value):
            return value

        # Total balance 0.01 ETH; one pending already allocates 0.0095, leaving
        # 0.0005. Required for new withdrawal is 0.001 + 0.0001 = 0.0011.
        monkeypatch.setattr(
            monitor_env,
            "_eth_balance",
            lambda address: asyncio.ensure_future(_coro(Decimal("0.01"))),
        )
        monkeypatch.setattr(
            monitor_env,
            "_eth_gas_price",
            lambda: asyncio.ensure_future(_coro(1_000_000_000)),
        )

        insert_withdrawal(
            ait_tx_hash="0xa" * 64,
            from_address="0x1111111111111111111111111111111111111111",
            eth_address="0x2222222222222222222222222222222222222222",
            amount_ait=Decimal("1"),
            fee_ait=Decimal("0.005"),
            net_ait=Decimal("0.995"),
            amount_eth=Decimal("0.001"),
        )

        with pytest.raises(RuntimeError, match="Insufficient ETH reserve"):
            await monitor_env._release_eth_for_withdrawal(
                withdrawal_id="withdrawal_abc",
                ait_tx_hash="0xa" * 64,
                eth_address="0x2222222222222222222222222222222222222222",
                amount_eth=Decimal("0.001"),
            )


class TestRefundWithdrawal:
    """_refund_withdrawal AIT refund path."""

    @pytest.mark.asyncio
    async def test_refund_success_updates_record(self, monitor_env, seed_withdrawal, monkeypatch):
        async def _submit_bridge_refund(recipient: str, amount_ait: Decimal) -> str:
            assert recipient == "0x1111111111111111111111111111111111111111"
            assert amount_ait == Decimal("10")
            return "0xait_refund_tx"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _submit_bridge_refund)

        await monitor_env._refund_withdrawal(
            ait_tx_hash=seed_withdrawal,
            user="0x1111111111111111111111111111111111111111",
            gross_ait=Decimal("10"),
            reason="release failed",
        )

        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "refunded"
        assert record["refund_tx_hash"] == "0xait_refund_tx"
        assert record["error"] == "release failed"

    @pytest.mark.asyncio
    async def test_refund_failure_marks_record_failed(self, monitor_env, seed_withdrawal, monkeypatch):
        async def _submit_bridge_refund(recipient: str, amount_ait: Decimal) -> str:
            raise RuntimeError("refund transaction rejected")

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _submit_bridge_refund)

        await monitor_env._refund_withdrawal(
            ait_tx_hash=seed_withdrawal,
            user="0x1111111111111111111111111111111111111111",
            gross_ait=Decimal("10"),
            reason="release failed",
        )

        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "failed"
        assert "refund transaction rejected" in record["error"]
