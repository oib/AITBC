"""Tests for the AIT->ETH withdrawal monitor.

Covers:
- reserve guard in _release_eth_for_withdrawal
- ETH-14: broadcast leaves the row 'releasing'; only a verified receipt
  may complete it (resume pass), never the broadcast echo
- _release_gas_limit: estimate x margin, floor, cap, fail-closed, override
- release failure with insufficient reserve
- _refund_withdrawal submits a refund transfer and updates the record
- refund failure marks the record failed
- _pending_eth_reserve sums pending/insufficient-reserve withdrawals
- ETH-14: releasing_retry rows park at needs_review_release on proven
  failure and are never auto-refunded
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
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
        # Static override so existing tests never reach eth_estimateGas;
        # gas-policy tests clear it and stub the RPC instead.
        monkeypatch.setattr(monitor, "ETH_WITHDRAW_GAS", "100000")
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

        # ETH-14: broadcast alone leaves the row 'releasing' — 'completed'
        # requires a status-1 receipt at depth, proven by the resume pass.
        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "releasing"
        assert record["eth_tx_hash"] == eth_tx_hash
        assert record["release_nonce"] == 7

        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionReceipt": {"status": "0x1", "blockNumber": "0x64"},
                "eth_blockNumber": "0x67",
            },
        )
        result = await monitor_env._resume_unfinished_releases()
        assert result["completed"] == 1
        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "completed"
        assert record["eth_tx_hash"] == eth_tx_hash

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


def _seed_releasing(ait_tx_hash: str, nonce: int = 7, status: str = "releasing") -> None:
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
    update_withdrawal_status(ait_tx_hash, status, eth_tx_hash="0x" + "ab" * 32, release_nonce=nonce)


def _backdate_release(ait_tx_hash: str, seconds: int) -> None:
    """Move the row's released_at (the release-intent write time) into the
    past — update_withdrawal_status always stamps now(), so age tests
    rewrite the column directly."""
    from wallet_app.bridge import bridge_db as db

    old = (datetime.now() - timedelta(seconds=seconds)).isoformat()
    conn = db._connect_db()
    conn.execute("UPDATE eth_withdrawals SET released_at = ? WHERE ait_tx_hash = ?", (old, ait_tx_hash))
    conn.commit()
    conn.close()


def _patch_rpc(monitor_env, monkeypatch, responses: dict):
    async def _fake_rpc(method: str, params: list):
        return responses.get(method)

    monkeypatch.setattr(monitor_env, "_eth_rpc", _fake_rpc)


def _patch_release_path(monitor_env, monkeypatch, broadcast_error=None):
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


class TestDuplicateReleaseSafety:
    """ETH-9: a post-send DB failure must never cause a refund on top of
    released ETH. Releasing rows carry nonce + deterministic hash so a
    restart can prove the outcome on-chain."""

    @pytest.mark.asyncio
    async def test_completed_write_fails_once_then_retries(self, monitor_env, seed_withdrawal, monkeypatch):
        """A transient DB error on 'completed' is retried, never falls to refund.

        ETH-14: the 'completed' write lives on the verified resume path —
        the broadcast itself only leaves 'releasing'."""
        _patch_release_path(monitor_env, monkeypatch)

        async def _broadcast(raw: str) -> str:
            return "0x" + "ab" * 32

        monkeypatch.setattr(monitor_env, "_broadcast_release_tx", _broadcast)
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionReceipt": {"status": "0x1", "blockNumber": "0x64"},
                "eth_blockNumber": "0x67",
            },
        )

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
        assert get_withdrawal_by_ait_tx_hash(seed_withdrawal)["status"] == "releasing"

        result = await monitor_env._resume_unfinished_releases()
        assert result["completed"] == 1
        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "completed"
        assert record["eth_tx_hash"] == eth_tx_hash
        assert calls["completed"] == 2  # retried, not skipped

    @pytest.mark.asyncio
    async def test_send_then_db_failure_no_refund_resume_completes(self, monitor_env, seed_withdrawal, monkeypatch):
        """The ETH-9/ETH-14 crash: send ok, then every 'completed' write
        fails — no refund may issue; once the DB recovers a later resume
        pass completes the row."""
        _patch_release_path(monitor_env, monkeypatch)

        async def _broadcast(raw: str) -> str:
            return "0x" + "ab" * 32

        monkeypatch.setattr(monitor_env, "_broadcast_release_tx", _broadcast)
        # Chain proves the release landed: receipt at block 0x64, chain at
        # 0x67 -> 4 confirmations, above the default depth of 3.
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionReceipt": {"status": "0x1", "blockNumber": "0x64"},
                "eth_blockNumber": "0x67",
            },
        )

        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xrefund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        await monitor_env._release_eth_for_withdrawal(
            "w1", seed_withdrawal, "0x2222222222222222222222222222222222222222", Decimal("0.001")
        )
        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "releasing"
        assert record["eth_tx_hash"].startswith("0x")
        assert record["release_nonce"] == 7

        real_update = monitor_env.update_withdrawal_status
        fail_completed = {"on": True}

        def flaky(ait_tx_hash, status, **kw):
            if status == "completed" and fail_completed["on"]:
                raise RuntimeError("db locked")
            return real_update(ait_tx_hash, status, **kw)

        monkeypatch.setattr(monitor_env, "update_withdrawal_status", flaky)

        # First resume: chain proves sent but every persist fails — the row
        # stays open, never refunded.
        first = await monitor_env._resume_unfinished_releases()
        assert first["still_open"] == 1
        assert refunded == []
        assert get_withdrawal_by_ait_tx_hash(seed_withdrawal)["status"] == "releasing"

        # Simulate restart: DB healthy again, resume completes the row.
        fail_completed["on"] = False
        result = await monitor_env._resume_unfinished_releases()
        assert result["completed"] == 1
        assert get_withdrawal_by_ait_tx_hash(seed_withdrawal)["status"] == "completed"
        assert refunded == []

    @pytest.mark.asyncio
    async def test_broadcast_failure_refunds_after_proof(self, monitor_env, seed_withdrawal, monkeypatch):
        """Broadcast raised and the chain shows nothing sent -> refund."""
        _patch_release_path(monitor_env, monkeypatch, broadcast_error=RuntimeError("connection reset"))
        # Nothing landed: no tx, no receipt, nonce still 7 (latest == pending).
        _patch_rpc(
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

        # The absence grace covers young rows only — backdate past it so
        # the proven-absent refund path is what this test exercises.
        _backdate_release(seed_withdrawal, monitor_env.ETH_RELEASE_ABSENCE_GRACE_SECONDS + 60)
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
        _patch_release_path(monitor_env, monkeypatch, broadcast_error=RuntimeError("connection reset"))
        _patch_rpc(
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
        _backdate_release(seed_withdrawal, monitor_env.ETH_RELEASE_ABSENCE_GRACE_SECONDS + 60)
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
        _seed_releasing("0x" + "cd" * 32)
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionReceipt": {"status": "0x1", "blockNumber": "0x64"},
                "eth_blockNumber": "0x67",
            },
        )

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
        """Restart with an old 'releasing' row that never reached chain -> refund."""
        _seed_releasing("0x" + "ef" * 32)
        # A crash-recovery row is naturally older than the absence grace —
        # absence-only 'not_sent' resolves exactly as before.
        _backdate_release("0x" + "ef" * 32, monitor_env.ETH_RELEASE_ABSENCE_GRACE_SECONDS + 60)
        _patch_rpc(
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
        _patch_release_path(monitor_env, monkeypatch, broadcast_error=RuntimeError("timeout"))

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

    @pytest.mark.asyncio
    async def test_manual_send_consumed_nonce_needs_review_no_refund(self, monitor_env, monkeypatch):
        """ETH-9b: a manual send from the bridge wallet can consume the
        recorded nonce while the recorded release never landed. A consumed
        nonce alone must never mark sent — the row stays open for review."""
        _seed_releasing("0x" + "ab" * 32, nonce=7)
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": None,
                # latest=8 > recorded nonce 7 — someone else's send took it.
                "eth_getTransactionCount": "0x8",
            },
        )
        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)
        result = await monitor_env._resume_unfinished_releases()
        assert result["still_open"] == 1
        assert result["completed"] == 0 and result["failed"] == 0
        assert refunded == []
        # Row is neither completed nor refunded — it stays for the operator.
        assert get_withdrawal_by_ait_tx_hash("0x" + "ab" * 32)["status"] == "releasing"

    @pytest.mark.asyncio
    async def test_receipt_below_depth_unknown_then_sent(self, monitor_env, monkeypatch):
        """ETH-9b: a successful receipt below the confirmation depth is
        'unknown'; the next poll re-checks and completes once depth is met."""
        _seed_releasing("0x" + "bc" * 32, nonce=7)
        chain_head = {"block": "0x67"}  # receipt at 0x66 -> depth 2 < 3

        async def _fake_rpc(method: str, params: list):
            if method == "eth_blockNumber":
                return chain_head["block"]
            return {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": {"status": "0x1", "blockNumber": "0x66"},
                "eth_getTransactionCount": "0x8",
            }.get(method)

        monkeypatch.setattr(monitor_env, "_eth_rpc", _fake_rpc)
        first = await monitor_env._resume_unfinished_releases()
        assert first["still_open"] == 1
        assert get_withdrawal_by_ait_tx_hash("0x" + "bc" * 32)["status"] == "releasing"
        # Chain advances: depth becomes 3 -> sent.
        chain_head["block"] = "0x68"
        second = await monitor_env._resume_unfinished_releases()
        assert second["completed"] == 1
        assert get_withdrawal_by_ait_tx_hash("0x" + "bc" * 32)["status"] == "completed"

    @pytest.mark.asyncio
    async def test_failed_receipt_not_sent_refunds_once(self, monitor_env, monkeypatch):
        """ETH-9b: a reverted release (receipt status 0) is proven not_sent —
        refund exactly once."""
        _seed_releasing("0x" + "de" * 32, nonce=7)
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": {"status": "0x0", "blockNumber": "0x64"},
                "eth_blockNumber": "0x67",
                "eth_getTransactionCount": "0x8",
            },
        )
        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)
        result = await monitor_env._resume_unfinished_releases()
        assert result["failed"] == 1
        assert len(refunded) == 1
        assert get_withdrawal_by_ait_tx_hash("0x" + "de" * 32)["status"] == "refunded"

    @pytest.mark.asyncio
    async def test_missing_row_verify_unknown(self, monitor_env):
        """ETH-9b: a withdrawal row that cannot be found proves nothing."""
        outcome = await monitor_env._verify_release_outcome("0x" + "f0" * 32)
        assert outcome == "unknown"

    @pytest.mark.asyncio
    async def test_rpc_error_verify_unknown(self, monitor_env, monkeypatch):
        """ETH-9b: any RPC failure during verification is 'unknown'."""
        _seed_releasing("0x" + "a1" * 32, nonce=7)

        async def _rpc_down(method: str, params: list):
            raise RuntimeError("rpc down")

        monkeypatch.setattr(monitor_env, "_eth_rpc", _rpc_down)
        assert await monitor_env._verify_release_outcome("0x" + "a1" * 32) == "unknown"


class TestReleaseGasPolicy:
    """ETH-14: _release_gas_limit — estimate x margin, floor, cap, fail closed.

    Post-Glamsterdam Sepolia a plain transfer to a fresh address estimates
    at ~207,391 (EIP-8037 state-gas) — a static 100k limit is a guaranteed
    out-of-gas revert. The release path must always estimate (or take the
    documented override) and refuse anything unverifiable.
    """

    def _estimator(self, monitor_env, monkeypatch, estimate_hex: str = "0x32a1f"):
        calls = []

        async def _rpc(method: str, params: list):
            calls.append((method, params))
            if method == "eth_estimateGas":
                return estimate_hex
            raise AssertionError(f"unexpected eth_rpc call {method}")

        monkeypatch.setattr(monitor_env, "_eth_rpc", _rpc)
        monkeypatch.setattr(monitor_env, "ETH_WITHDRAW_GAS", "")
        return calls

    @pytest.mark.asyncio
    async def test_estimate_times_margin(self, monitor_env, monkeypatch):
        """207,391 x 1.25 = 259,238.75 -> ceil 259,239."""
        calls = self._estimator(monitor_env, monkeypatch, "0x32a1f")
        limit = await monitor_env._release_gas_limit("0x2222222222222222222222222222222222222222", Decimal("0.001"))
        assert limit == 259_239
        # The estimate call carries the exact (from, to, value) tuple.
        assert calls[0][0] == "eth_estimateGas"
        call = calls[0][1][0]
        assert call["to"] == "0x2222222222222222222222222222222222222222"
        assert call["value"] == hex(int(Decimal("0.001") * 10**18))
        assert call["from"].lower() == TEST_ETH_ADDRESS.lower()

    @pytest.mark.asyncio
    async def test_floor_applies_below_21000(self, monitor_env, monkeypatch):
        """A 15,000 estimate x 1.25 = 18,750 -> floored to 21,000."""
        self._estimator(monitor_env, monkeypatch, hex(15_000))
        limit = await monitor_env._release_gas_limit("0x2222222222222222222222222222222222222222", Decimal("0.001"))
        assert limit == 21_000

    @pytest.mark.asyncio
    async def test_estimate_over_cap_fails_closed(self, monitor_env, monkeypatch):
        """500k x 1.25 exceeds the 300k cap -> raise before any signing."""
        self._estimator(monitor_env, monkeypatch, hex(500_000))
        with pytest.raises(RuntimeError, match="ETH_WITHDRAW_GAS_MAX"):
            await monitor_env._release_gas_limit("0x2222222222222222222222222222222222222222", Decimal("0.001"))

    @pytest.mark.asyncio
    async def test_estimate_rpc_error_fails_closed(self, monitor_env, monkeypatch):
        async def _rpc_down(method: str, params: list):
            raise RuntimeError("rpc down")

        monkeypatch.setattr(monitor_env, "_eth_rpc", _rpc_down)
        monkeypatch.setattr(monitor_env, "ETH_WITHDRAW_GAS", "")
        with pytest.raises(RuntimeError):
            await monitor_env._release_gas_limit("0x2222222222222222222222222222222222222222", Decimal("0.001"))

    @pytest.mark.asyncio
    async def test_estimate_failure_never_broadcasts(self, monitor_env, seed_withdrawal, monkeypatch):
        """An estimation error raises before intent persist or broadcast —
        _resolve_release_failure then proves 'not_sent' (no hash, no nonce)
        and refunds."""
        sent: list[str] = []

        async def _broadcast(raw: str) -> str:
            sent.append(raw)
            return "0x" + "ab" * 32

        monkeypatch.setattr(monitor_env, "_broadcast_release_tx", _broadcast)
        monkeypatch.setattr(monitor_env, "ETH_WITHDRAW_GAS", "")

        async def _coro(value):
            return value

        monkeypatch.setattr(monitor_env, "_eth_gas_price", lambda: asyncio.ensure_future(_coro(1_000_000_000)))

        async def _rpc(method: str, params: list):
            if method == "eth_estimateGas":
                raise RuntimeError("estimation failed")
            return None  # outcome verification: nothing on chain

        monkeypatch.setattr(monitor_env, "_eth_rpc", _rpc)
        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        with pytest.raises(RuntimeError, match="estimation failed"):
            await monitor_env._release_eth_for_withdrawal(
                "w1", seed_withdrawal, "0x2222222222222222222222222222222222222222", Decimal("0.001")
            )
        assert sent == []
        # No intent was persisted — the row cannot look sent.
        record = get_withdrawal_by_ait_tx_hash(seed_withdrawal)
        assert record["status"] == "pending"
        assert record["eth_tx_hash"] is None
        assert record["release_nonce"] is None
        await monitor_env._resolve_release_failure(
            seed_withdrawal, "0x1111111111111111111111111111111111111111", Decimal("10"), RuntimeError("x")
        )
        assert get_withdrawal_by_ait_tx_hash(seed_withdrawal)["status"] == "refunded"
        assert len(refunded) == 1

    @pytest.mark.asyncio
    async def test_explicit_override_skips_estimate(self, monitor_env, monkeypatch):
        """ETH_WITHDRAW_GAS=250000 override is honoured without any RPC."""

        async def _rpc(method: str, params: list):
            raise AssertionError("estimate must not be called under the override")

        monkeypatch.setattr(monitor_env, "_eth_rpc", _rpc)
        monkeypatch.setattr(monitor_env, "ETH_WITHDRAW_GAS", "250000")
        limit = await monitor_env._release_gas_limit("0x2222222222222222222222222222222222222222", Decimal("0.001"))
        assert limit == 250_000

    @pytest.mark.asyncio
    async def test_override_over_cap_fails(self, monitor_env, monkeypatch):
        monkeypatch.setattr(monitor_env, "ETH_WITHDRAW_GAS", "400000")
        with pytest.raises(RuntimeError, match="outside"):
            await monitor_env._release_gas_limit("0x2222222222222222222222222222222222222222", Decimal("0.001"))

    @pytest.mark.asyncio
    async def test_release_uses_estimated_gas_in_signed_tx(self, monitor_env, seed_withdrawal, monkeypatch):
        """End-to-end: with the override cleared the signed tx carries the
        margined estimate, not a static limit."""

        async def _coro(value):
            return value

        monkeypatch.setattr(monitor_env, "_eth_balance", lambda a: asyncio.ensure_future(_coro(Decimal("0.1"))))
        monkeypatch.setattr(monitor_env, "_eth_gas_price", lambda: asyncio.ensure_future(_coro(1_000_000_000)))
        monkeypatch.setattr(monitor_env, "_eth_nonce", lambda a: asyncio.ensure_future(_coro(7)))
        monkeypatch.setattr(monitor_env, "ETH_WITHDRAW_GAS", "")

        async def _rpc(method: str, params: list):
            if method == "eth_estimateGas":
                return "0x32a1f"  # 207,391 — the post-Glamsterdam fresh-account cost
            raise AssertionError(f"unexpected {method}")

        monkeypatch.setattr(monitor_env, "_eth_rpc", _rpc)
        sent = []

        async def _broadcast(raw: str) -> str:
            sent.append(raw)
            return "0x" + "ab" * 32

        monkeypatch.setattr(monitor_env, "_broadcast_release_tx", _broadcast)
        await monitor_env._release_eth_for_withdrawal(
            "w1", seed_withdrawal, "0x2222222222222222222222222222222222222222", Decimal("0.001")
        )
        assert len(sent) == 1
        # Legacy typed-0 tx: rlp fields [nonce, gasPrice, gas, to, value, data, v, r, s]
        import rlp

        decoded = rlp.decode(bytes.fromhex(sent[0][2:]))
        gas_field = int.from_bytes(decoded[2], "big")
        assert gas_field == 259_239


class TestRetryResumeStatuses:
    """ETH-14: operator retry statuses — releasing_retry parks on proven
    failure instead of auto-refunding; needs_review_release is terminal
    for the machine (operator-only)."""

    @pytest.mark.asyncio
    async def test_releasing_retry_reverted_parks_no_refund(self, monitor_env, monkeypatch):
        """A retry whose receipt proves reverted parks at
        needs_review_release — the refund decision stays with the operator."""
        _seed_releasing("0x" + "b1" * 32, nonce=8, status="releasing_retry")
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": {"status": "0x0", "blockNumber": "0x64"},
                "eth_blockNumber": "0x67",
                "eth_getTransactionCount": "0x9",
            },
        )
        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)
        result = await monitor_env._resume_unfinished_releases()
        assert result["parked"] == 1
        assert result["failed"] == 0
        assert refunded == []
        record = get_withdrawal_by_ait_tx_hash("0x" + "b1" * 32)
        assert record["status"] == "needs_review_release"
        assert record["refund_tx_hash"] is None

    @pytest.mark.asyncio
    async def test_releasing_retry_sent_completes(self, monitor_env, monkeypatch):
        """A retry verified sent completes the row the same as any release."""
        _seed_releasing("0x" + "b2" * 32, nonce=8, status="releasing_retry")
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionReceipt": {"status": "0x1", "blockNumber": "0x64"},
                "eth_blockNumber": "0x67",
            },
        )
        result = await monitor_env._resume_unfinished_releases()
        assert result["completed"] == 1
        assert get_withdrawal_by_ait_tx_hash("0x" + "b2" * 32)["status"] == "completed"

    @pytest.mark.asyncio
    async def test_needs_review_release_not_resumed(self, monitor_env, monkeypatch):
        """Parked retry rows are not machine-resumable — only an operator
        action (release-retry or mark-review) may move them."""
        _seed_releasing("0x" + "b3" * 32, nonce=8, status="needs_review_release")
        result = await monitor_env._resume_unfinished_releases()
        assert result == {"completed": 0, "failed": 0, "parked": 0, "still_open": 0}
        assert get_withdrawal_by_ait_tx_hash("0x" + "b3" * 32)["status"] == "needs_review_release"


class TestAbsenceGrace:
    """ETH-14b: a lagging / load-balanced RPC can report a just-broadcast
    release as absent (no tx, no receipt, nonce not pending). Treating
    that view as 'not_sent' refunds a send that may still seal — a double
    pay. Inside ETH_RELEASE_ABSENCE_GRACE_SECONDS an absence-only result
    is 'unknown'; a reverted receipt stays 'not_sent' at any age."""

    _ABSENT_RPC = {
        "eth_getTransactionByHash": None,
        "eth_getTransactionReceipt": None,
        "eth_getTransactionCount": "0x7",  # recorded nonce 7 — not consumed, not pending
    }

    @pytest.mark.asyncio
    async def test_young_absent_release_reports_unknown_no_refund(self, monitor_env, monkeypatch):
        ait = "0x" + "e1" * 32
        _seed_releasing(ait)
        _patch_rpc(monitor_env, monkeypatch, dict(self._ABSENT_RPC))

        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        result = await monitor_env._resume_unfinished_releases()
        assert result["still_open"] == 1
        assert result["failed"] == 0
        assert refunded == []
        assert get_withdrawal_by_ait_tx_hash(ait)["status"] == "releasing"

    @pytest.mark.asyncio
    async def test_old_absent_release_reports_not_sent_refunds(self, monitor_env, monkeypatch):
        ait = "0x" + "e2" * 32
        _seed_releasing(ait)
        _backdate_release(ait, monitor_env.ETH_RELEASE_ABSENCE_GRACE_SECONDS + 60)
        _patch_rpc(monitor_env, monkeypatch, dict(self._ABSENT_RPC))

        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        result = await monitor_env._resume_unfinished_releases()
        assert result["failed"] == 1
        assert len(refunded) == 1
        assert get_withdrawal_by_ait_tx_hash(ait)["status"] == "refunded"

    @pytest.mark.asyncio
    async def test_young_reverted_receipt_still_not_sent(self, monitor_env, monkeypatch):
        """A status-0 receipt is unambiguous — proven failure at any age,
        no grace delay before the refund."""
        ait = "0x" + "e3" * 32
        _seed_releasing(ait)
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": {"status": "0x0", "blockNumber": "0x64"},
                "eth_blockNumber": "0x67",
                "eth_getTransactionCount": "0x8",
            },
        )
        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        result = await monitor_env._resume_unfinished_releases()
        assert result["failed"] == 1
        assert len(refunded) == 1
        assert get_withdrawal_by_ait_tx_hash(ait)["status"] == "refunded"

    @pytest.mark.asyncio
    async def test_young_absent_retry_stays_open_not_parked(self, monitor_env, monkeypatch):
        """releasing_retry takes the same grace: absent while young is
        'unknown' — it must NOT park at needs_review_release (that state
        means *proven* failure, not 'cannot see the tx yet')."""
        ait = "0x" + "e4" * 32
        _seed_releasing(ait, nonce=8, status="releasing_retry")
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": None,
                "eth_getTransactionCount": "0x8",
            },
        )
        result = await monitor_env._resume_unfinished_releases()
        assert result["still_open"] == 1
        assert result["parked"] == 0
        assert get_withdrawal_by_ait_tx_hash(ait)["status"] == "releasing_retry"

    @pytest.mark.asyncio
    async def test_old_absent_retry_parks(self, monitor_env, monkeypatch):
        """Past the grace window the same absence is 'not_sent' — a retry
        parks for the operator, still never auto-refunded."""
        ait = "0x" + "e5" * 32
        _seed_releasing(ait, nonce=8, status="releasing_retry")
        _backdate_release(ait, monitor_env.ETH_RELEASE_ABSENCE_GRACE_SECONDS + 60)
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": None,
                "eth_getTransactionCount": "0x8",
            },
        )
        refunded = []

        async def _refund(recipient, amount):
            refunded.append((recipient, amount))
            return "0xait_refund"

        monkeypatch.setattr(monitor_env, "_submit_bridge_refund", _refund)

        result = await monitor_env._resume_unfinished_releases()
        assert result["parked"] == 1
        assert refunded == []
        assert get_withdrawal_by_ait_tx_hash(ait)["status"] == "needs_review_release"


class TestGraceLogLevel:
    """ETH-15: an in-grace absence is routine propagation lag — logged at
    INFO, never ERROR. 'unknown' for any other reason (or past the grace
    window) stays ERROR, since it means genuinely unverifiable."""

    _ABSENT_RPC = {
        "eth_getTransactionByHash": None,
        "eth_getTransactionReceipt": None,
        "eth_getTransactionCount": "0x7",  # recorded nonce 7 — free, not pending
    }

    def _monitor_records(self, caplog):
        return [(r.levelno, r.getMessage()) for r in caplog.records if r.name == "wallet_app.bridge.bridge_withdraw_monitor"]

    @pytest.mark.asyncio
    async def test_in_grace_absence_logs_info_not_error(self, monitor_env, monkeypatch, caplog):
        ait = "0x" + "f1" * 32
        _seed_releasing(ait)
        _patch_rpc(monitor_env, monkeypatch, dict(self._ABSENT_RPC))

        with caplog.at_level(logging.INFO, logger="wallet_app.bridge.bridge_withdraw_monitor"):
            result = await monitor_env._resume_unfinished_releases()

        assert result["still_open"] == 1
        msgs = self._monitor_records(caplog)
        assert any(lvl == logging.INFO and "absence grace" in m for lvl, m in msgs)
        assert not any(lvl >= logging.ERROR for lvl, m in msgs)

    @pytest.mark.asyncio
    async def test_non_absence_unknown_still_errors(self, monitor_env, monkeypatch, caplog):
        """Nonce consumed without a qualifying receipt is 'unknown' for a
        real reason — ERROR even on a young row."""
        ait = "0x" + "f2" * 32
        _seed_releasing(ait, nonce=7)
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": None,
                "eth_getTransactionReceipt": None,
                "eth_getTransactionCount": "0x9",  # nonce 7 spent, hash unseen
            },
        )

        with caplog.at_level(logging.INFO, logger="wallet_app.bridge.bridge_withdraw_monitor"):
            result = await monitor_env._resume_unfinished_releases()

        assert result["still_open"] == 1
        msgs = self._monitor_records(caplog)
        assert any(lvl >= logging.ERROR and "unverifiable" in m for lvl, m in msgs)
        assert not any(lvl == logging.INFO and "absence grace" in m for lvl, m in msgs)

    @pytest.mark.asyncio
    async def test_unknown_after_grace_still_errors(self, monitor_env, monkeypatch, caplog):
        """A tx seen by the node but unmined stays 'unknown' past grace —
        ERROR, not the routine in-grace INFO."""
        ait = "0x" + "f3" * 32
        _seed_releasing(ait)
        _backdate_release(ait, monitor_env.ETH_RELEASE_ABSENCE_GRACE_SECONDS + 60)
        _patch_rpc(
            monitor_env,
            monkeypatch,
            {
                "eth_getTransactionByHash": {"hash": "0x" + "ab" * 32},
                "eth_getTransactionReceipt": None,
            },
        )

        with caplog.at_level(logging.INFO, logger="wallet_app.bridge.bridge_withdraw_monitor"):
            result = await monitor_env._resume_unfinished_releases()

        assert result["still_open"] == 1
        msgs = self._monitor_records(caplog)
        assert any(lvl >= logging.ERROR and "unverifiable" in m for lvl, m in msgs)
