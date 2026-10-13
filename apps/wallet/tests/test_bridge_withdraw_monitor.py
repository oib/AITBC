"""Tests for the AIT->ETH withdrawal monitor.

Covers:
- reserve guard in _release_eth_for_withdrawal
- successful ETH release updates the withdrawal record
- release failure with insufficient reserve
- _refund_withdrawal submits a refund transfer and updates the record
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

        async def _nonce(address):
            return 7

        async def _broadcast(raw: str) -> str:
            sent.append(raw)
            return "0xeth_release_tx"

        monkeypatch.setattr(monitor_env, "_eth_nonce", _nonce)
        monkeypatch.setattr(monitor_env, "_broadcast_release_tx", _broadcast)

        eth_tx_hash = await monitor_env._release_eth_for_withdrawal(
            withdrawal_id="withdrawal_abc",
            ait_tx_hash=seed_withdrawal,
            eth_address="0x2222222222222222222222222222222222222222",
            amount_eth=Decimal("0.001"),
        )

        # The deterministic signed hash is authoritative, not the broadcast echo.
        assert eth_tx_hash.startswith("0x") and len(eth_tx_hash) == 66
        assert len(sent) == 1

        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "completed"
        assert record["eth_tx_hash"] == eth_tx_hash
        assert record["release_nonce"] == 7

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


class TestDuplicateReleaseSafety:
    """ETH-9: a post-send DB failure must never cause a refund on top of
    released ETH. Releasing rows carry nonce + deterministic hash so a
    restart can prove the outcome on-chain."""

    def _seed_releasing(self, ait_tx_hash: str, nonce: int = 7) -> None:
        from wallet_app.bridge.bridge_db import update_withdrawal_status

        insert_withdrawal(
            ait_tx_hash=ait_tx_hash,
            from_address="0x1111111111111111111111111111111111111111",
            eth_address="0x2222222222222222222222222222222222222222",
            amount_ait=Decimal("10"),
            fee_ait=Decimal("0.05"),
            net_ait=Decimal("9.95"),
            amount_eth=Decimal("0.001"),
        )
        update_withdrawal_status(ait_tx_hash, "releasing", eth_tx_hash="0x" + "ab" * 32, release_nonce=nonce)

    def _patch_rpc(self, monitor_env, monkeypatch, responses: dict):
        async def _fake_rpc(method: str, params: list):
            return responses.get(method)

        monkeypatch.setattr(monitor_env, "_eth_rpc", _fake_rpc)

    def _patch_release_path(self, monitor_env, monkeypatch, broadcast_error=None):
        async def _coro(value):
            return value

        monkeypatch.setattr(monitor_env, "_eth_balance", lambda a: asyncio.ensure_future(_coro(Decimal("0.1"))))
        monkeypatch.setattr(monitor_env, "_eth_gas_price", lambda: asyncio.ensure_future(_coro(1_000_000_000)))
        monkeypatch.setattr(monitor_env, "_eth_nonce", lambda a: asyncio.ensure_future(_coro(7)))
        monkeypatch.setattr(monitor_env, "_STATUS_PERSIST_DELAYS", (0, 0))

        if broadcast_error is not None:

            async def _broadcast(raw: str) -> str:
                raise broadcast_error

            monkeypatch.setattr(monitor_env, "_broadcast_release_tx", _broadcast)

    @pytest.mark.asyncio
    async def test_completed_write_fails_once_then_retries(self, monitor_env, seed_withdrawal, monkeypatch):
        """A transient DB error on 'completed' is retried, never falls to refund."""
        self._patch_release_path(monitor_env, monkeypatch)

        async def _broadcast(raw: str) -> str:
            return "0x" + "ab" * 32

        monkeypatch.setattr(monitor_env, "_broadcast_release_tx", _broadcast)

        real_update = monitor_env.update_withdrawal_status
        calls = {"completed": 0}

        def flaky(ait_tx_hash, status, **kw):
            if status == "completed":
                calls["completed"] += 1
                if calls["completed"] == 1:
                    raise RuntimeError("db locked")
            return real_update(ait_tx_hash, status, **kw)

        monkeypatch.setattr(monitor_env, "update_withdrawal_status", flaky)

        eth_tx_hash = await monitor_env._release_eth_for_withdrawal(
            "w1", seed_withdrawal, "0x2222222222222222222222222222222222222222", Decimal("0.001")
        )

        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "completed"
        assert record["eth_tx_hash"] == eth_tx_hash
        assert calls["completed"] == 2  # retried, not skipped

    @pytest.mark.asyncio
    async def test_send_then_db_failure_no_refund_resume_completes(self, monitor_env, seed_withdrawal, monkeypatch):
        """The ETH-9 crash: send ok, 'completed' write fails, verify proves
        sent -> no refund; a later resume pass completes the row."""
        self._patch_release_path(monitor_env, monkeypatch)

        async def _broadcast(raw: str) -> str:
            return "0x" + "ab" * 32

        monkeypatch.setattr(monitor_env, "_broadcast_release_tx", _broadcast)
        # Chain proves the release landed.
        self._patch_rpc(monitor_env, monkeypatch, {"eth_getTransactionReceipt": {"status": "0x1"}})

        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xrefund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        real_update = monitor_env.update_withdrawal_status
        fail_completed = {"on": True}

        def flaky(ait_tx_hash, status, **kw):
            if status == "completed" and fail_completed["on"]:
                raise RuntimeError("db locked")
            return real_update(ait_tx_hash, status, **kw)

        monkeypatch.setattr(monitor_env, "update_withdrawal_status", flaky)

        with pytest.raises(RuntimeError, match="could not persist"):
            await monitor_env._release_eth_for_withdrawal(
                "w1", seed_withdrawal, "0x2222222222222222222222222222222222222222", Decimal("0.001")
            )

        # Send succeeded, persist failed -> the except path must NOT refund.
        await monitor_env._resolve_release_failure(
            seed_withdrawal, "0x1111111111111111111111111111111111111111", Decimal("10"), RuntimeError("boom")
        )
        assert refunded == []
        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "releasing"
        assert record["eth_tx_hash"].startswith("0x")
        assert record["release_nonce"] == 7

        # Simulate restart: DB healthy again, resume completes the row.
        fail_completed["on"] = False
        result = await monitor_env._resume_unfinished_releases()
        assert result["completed"] == 1
        assert get_withdrawal_by_ait_tx_hash(seed_withdrawal)["status"] == "completed"
        assert refunded == []

    @pytest.mark.asyncio
    async def test_broadcast_failure_refunds_after_proof(self, monitor_env, seed_withdrawal, monkeypatch):
        """Broadcast raised and the chain shows nothing sent -> refund."""
        self._patch_release_path(monitor_env, monkeypatch, broadcast_error=RuntimeError("connection reset"))
        # Nothing landed: no tx, no receipt, nonce still 7 (latest == pending).
        self._patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": None,
                "eth_getTransactionCount": "0x7",
            },
        )

        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        with pytest.raises(RuntimeError, match="connection reset"):
            await monitor_env._release_eth_for_withdrawal(
                "w1", seed_withdrawal, "0x2222222222222222222222222222222222222222", Decimal("0.001")
            )

        await monitor_env._resolve_release_failure(
            seed_withdrawal,
            "0x1111111111111111111111111111111111111111",
            Decimal("10"),
            RuntimeError("connection reset"),
        )
        assert len(refunded) == 1
        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "refunded"
        assert record["refund_tx_hash"] == "0xait_refund"

    @pytest.mark.asyncio
    async def test_refund_failure_marks_failed_single_attempt(self, monitor_env, seed_withdrawal, monkeypatch):
        """A failed refund marks the row failed without a second refund try."""
        self._patch_release_path(monitor_env, monkeypatch, broadcast_error=RuntimeError("connection reset"))
        self._patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": None,
                "eth_getTransactionCount": "0x7",
            },
        )

        calls = []

        async def _refund(recipient, amount):
            calls.append((recipient, amount))
            raise RuntimeError("refund tx rejected")

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        with pytest.raises(RuntimeError):
            await monitor_env._release_eth_for_withdrawal(
                "w1", seed_withdrawal, "0x2222222222222222222222222222222222222222", Decimal("0.001")
            )
        await monitor_env._resolve_release_failure(
            seed_withdrawal,
            "0x1111111111111111111111111111111111111111",
            Decimal("10"),
            RuntimeError("connection reset"),
        )

        assert len(calls) == 1
        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "failed"
        assert record["refund_tx_hash"] is None
        assert "refund tx rejected" in record["error"]

    @pytest.mark.asyncio
    async def test_restart_releasing_row_tx_on_chain_completes(self, monitor_env, monkeypatch):
        """Restart with a 'releasing' row whose receipt exists -> completed."""
        self._seed_releasing("0x" + "cd" * 32)
        self._patch_rpc(monitor_env, monkeypatch, {"eth_getTransactionReceipt": {"status": "0x1"}})

        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)
        monkeypatch.setattr(monitor_env, "_STATUS_PERSIST_DELAYS", (0, 0))

        result = await monitor_env._resume_unfinished_releases()
        assert result["completed"] == 1
        assert get_withdrawal_by_ait_tx_hash("0x" + "cd" * 32)["status"] == "completed"
        assert refunded == []

    @pytest.mark.asyncio
    async def test_restart_releasing_row_no_tx_refunds(self, monitor_env, monkeypatch):
        """Restart with a 'releasing' row that never reached chain -> refund."""
        self._seed_releasing("0x" + "ef" * 32)
        self._patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": None,
                "eth_getTransactionCount": "0x7",
            },
        )

        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        result = await monitor_env._resume_unfinished_releases()
        assert result["failed"] == 1
        record = get_withdrawal_by_ait_tx_hash("0x" + "ef" * 32)
        assert record["status"] == "refunded"
        assert record["refund_tx_hash"] == "0xait_refund"
        assert len(refunded) == 1

    @pytest.mark.asyncio
    async def test_rpc_down_marks_needs_review_never_refunds(self, monitor_env, seed_withdrawal, monkeypatch):
        """Unverifiable outcome -> needs_review, never a blind refund."""
        self._patch_release_path(monitor_env, monkeypatch, broadcast_error=RuntimeError("timeout"))

        async def _rpc_down(method, params):
            raise RuntimeError("rpc down")

        monkeypatch.setattr(monitor_env, "_eth_rpc", _rpc_down)

        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        with pytest.raises(RuntimeError):
            await monitor_env._release_eth_for_withdrawal(
                "w1", seed_withdrawal, "0x2222222222222222222222222222222222222222", Decimal("0.001")
            )
        await monitor_env._resolve_release_failure(
            seed_withdrawal,
            "0x1111111111111111111111111111111111111111",
            Decimal("10"),
            RuntimeError("timeout"),
        )
        assert refunded == []
        assert get_withdrawal_by_ait_tx_hash(seed_withdrawal)["status"] == "needs_review"
