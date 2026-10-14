"""Tests for wallet_app.bridge.withdraw_admin (ETH-14 operator commands).

The commands are exercised through main() so the real argument parsing,
env-file loading, eligibility checks, proof bundle, intent persistence and
attempt recording all run — only the network seams (_rpc_call,
_ait_rpc_get, wdm._eth_rpc/_broadcast_release_tx) are stubbed.
"""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from wallet_app.bridge.bridge_db import (
    get_release_attempts,
    get_withdrawal_by_ait_tx_hash,
    init_db,
    insert_withdrawal,
    update_withdrawal_status,
)

TEST_ETH_PRIVATE_KEY = "0x" + "11" * 32
TEST_ETH_ADDRESS = "0x19E7E376E7C213B7E7e7e46cc70A5dD086DAff2A"

RPC_A = "http://rpc-a.test"
RPC_B = "http://rpc-b.test"
AIT_HASH = "0xa" * 64
OLD_ETH_TX = "0x" + "ab" * 32
ETH_TO = "0x2222222222222222222222222222222222222222"

# Dict-valued RPC answers key off this param index per method.
_KEY_INDEX = {"eth_getTransactionCount": 1}


def _stub_network(monkeypatch: pytest.MonkeyPatch, admin, wdm, state: dict) -> None:
    """Patch every network seam on admin + wdm to read from `state`."""

    async def _rpc_call(url: str, method: str, params: list):
        value = state["rpc"].get(url, {}).get(method)
        if callable(value):
            return value(params)
        if isinstance(value, dict):
            return value.get(params[_KEY_INDEX.get(method, 0)] if params else None)
        return value

    async def _ait_get(url: str):
        return state["ait_status"]

    async def _wdm_rpc(method: str, params: list):
        if method == "eth_estimateGas":
            return "0x32a1f"  # 207,391 — post-Glamsterdam fresh-account cost
        raise AssertionError(f"unexpected wdm._eth_rpc {method}")

    async def _broadcast(raw: str) -> str:
        state["sent"].append(raw)
        # Intent must already be persisted before this call returns.
        row = get_withdrawal_by_ait_tx_hash(AIT_HASH)
        assert row["status"] == "releasing_retry"
        assert row["eth_tx_hash"].startswith("0x")
        return row["eth_tx_hash"]

    async def _verify(ait_tx_hash: str) -> str:
        return state["verify_outcome"]

    async def _coro(value):
        return value

    monkeypatch.setattr(admin, "_rpc_call", _rpc_call)
    monkeypatch.setattr(admin, "_ait_rpc_get", _ait_get)
    monkeypatch.setattr(admin, "_RETRY_OUTCOME_WAIT_SECONDS", 0)
    monkeypatch.setattr(admin, "_RETRY_OUTCOME_POLL_SECONDS", 0)
    monkeypatch.setattr(wdm, "_eth_rpc", _wdm_rpc)
    monkeypatch.setattr(wdm, "_eth_gas_price", lambda: asyncio.ensure_future(_coro(1_000_000_000)))
    monkeypatch.setattr(wdm, "_eth_balance", lambda a: asyncio.ensure_future(_coro(Decimal("0.1"))))
    monkeypatch.setattr(wdm, "_broadcast_release_tx", _broadcast)
    monkeypatch.setattr(wdm, "_verify_release_outcome", _verify)
    monkeypatch.setattr(wdm, "_STATUS_PERSIST_DELAYS", (0, 0))
    monkeypatch.setattr(wdm, "ETH_WITHDRAW_GAS", "")


@pytest.fixture
def admin_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Env file + seeded bridge DB + fully stubbed network seams."""
    import wallet_app.bridge.bridge_withdraw_monitor as wdm
    import wallet_app.bridge.withdraw_admin as admin

    db_path = tmp_path / "bridge.db"
    env_path = tmp_path / "ops.env"
    env_path.write_text(
        f"ETH_RPC_URL={RPC_A}\n"
        f"ETH_VERIFY_RPC_URL={RPC_B}\n"
        f"ETH_WALLET_ADDRESS={TEST_ETH_ADDRESS}\n"
        f"ETH_WALLET_PRIVATE_KEY={TEST_ETH_PRIVATE_KEY}\n"
        "BRIDGE_ENABLED=true\n"
        "BLOCKCHAIN_RPC_URL=http://chain.test\n"
    )
    env_keys = (
        "ETH_RPC_URL",
        "ETH_VERIFY_RPC_URL",
        "ETH_WALLET_ADDRESS",
        "ETH_WALLET_PRIVATE_KEY",
        "BRIDGE_ENABLED",
        "BLOCKCHAIN_RPC_URL",
    )
    saved_env = {k: os.environ.get(k) for k in env_keys}
    monkeypatch.delenv("ETH_WITHDRAW_GAS", raising=False)

    state: dict = {
        # per-endpoint per-method canned answers; tests fill in
        "rpc": {RPC_A: {}, RPC_B: {}},
        "sent": [],
        "ait_status": {"status": "confirmed", "block_height": 46750},
        "verify_outcome": "sent",
    }
    _stub_network(monkeypatch, admin, wdm, state)

    with patch("wallet_app.bridge.bridge_db.DB_PATH", str(db_path)):
        init_db()
        yield state, env_path, db_path

    for key, val in saved_env.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


def _seed_completed_row(status: str = "completed") -> None:
    insert_withdrawal(
        ait_tx_hash=AIT_HASH,
        from_address="0x1111111111111111111111111111111111111111",
        eth_address=ETH_TO,
        amount_ait=Decimal("10"),
        fee_ait=Decimal("0.05"),
        net_ait=Decimal("9.95"),
        amount_eth=Decimal("0.00111306005378485"),
    )
    update_withdrawal_status(AIT_HASH, status, eth_tx_hash=OLD_ETH_TX, release_nonce=0)


def _reverted_rpc(latest_nonce: int = 1) -> dict:
    """A per-endpoint answer set proving the recorded release reverted."""
    return {
        "eth_getTransactionReceipt": {OLD_ETH_TX: {"status": "0x0", "blockNumber": hex(0xB5C122)}},
        "eth_getTransactionByHash": {OLD_ETH_TX: {"hash": OLD_ETH_TX}},
        "eth_blockNumber": hex(0xB5C200),
        "eth_getBalance": hex(0),
        "eth_getTransactionCount": {"latest": hex(latest_nonce)},
    }


def _never_mined_rpc(latest_nonce: int = 1) -> dict:
    """The recorded retry hash absent everywhere; its nonce still free."""
    return {
        "eth_getTransactionReceipt": {},
        "eth_getTransactionByHash": {},
        "eth_blockNumber": hex(0xB5C200),
        "eth_getTransactionCount": {"latest": hex(latest_nonce)},
    }


def _run(argv: list[str]) -> int:
    import wallet_app.bridge.withdraw_admin as admin

    return admin.main(argv)


class TestStatusCommand:
    def test_status_shows_row_and_proofs(self, admin_env, capsys):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "status", AIT_HASH])
        assert rc == 0
        out = capsys.readouterr().out
        assert "withdrawal_" in out
        assert "reverted" in out


class TestReleaseRetry:
    def test_dry_run_makes_no_writes(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH])
        assert rc == 0
        row = get_withdrawal_by_ait_tx_hash(AIT_HASH)
        assert row["status"] == "completed"  # untouched
        assert row["eth_tx_hash"] == OLD_ETH_TX
        assert get_release_attempts(AIT_HASH) == []
        assert state["sent"] == []

    def test_refuses_without_second_rpc(self, admin_env):
        state, _, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        # Env file without ETH_VERIFY_RPC_URL — only the primary endpoint.
        single_env = Path(str(db_path)).parent / "ops-single.env"
        single_env.write_text(
            f"ETH_RPC_URL={RPC_A}\n"
            f"ETH_WALLET_ADDRESS={TEST_ETH_ADDRESS}\n"
            f"ETH_WALLET_PRIVATE_KEY={TEST_ETH_PRIVATE_KEY}\n"
            "BRIDGE_ENABLED=true\n"
            "BLOCKCHAIN_RPC_URL=http://chain.test\n"
        )

        rc = _run(["--env-file", str(single_env), "--db", str(db_path), "release-retry", AIT_HASH])
        assert rc == 1
        assert state["sent"] == []

    def test_refuses_when_receipt_sent(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        sent = _reverted_rpc()
        sent["eth_getTransactionReceipt"] = {OLD_ETH_TX: {"status": "0x1", "blockNumber": hex(0xB5C122)}}
        state["rpc"][RPC_A] = sent
        state["rpc"][RPC_B] = _reverted_rpc()

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH])
        assert rc == 1
        assert get_withdrawal_by_ait_tx_hash(AIT_HASH)["status"] == "completed"
        assert state["sent"] == []

    def test_refuses_wrong_status(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row(status="pending")
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH])
        assert rc == 1
        assert state["sent"] == []

    def test_refuses_refunded_row(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        update_withdrawal_status(AIT_HASH, "refunded", refund_tx_hash="0x" + "cc" * 32)
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH])
        assert rc == 1
        assert state["sent"] == []

    def test_refuses_on_nonce_disagreement(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc(latest_nonce=1)
        state["rpc"][RPC_B] = _reverted_rpc(latest_nonce=2)

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH])
        assert rc == 1
        assert state["sent"] == []

    def test_refuses_when_ait_leg_not_sealed(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()
        state["ait_status"] = {"status": "pending"}

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH])
        assert rc == 1
        assert state["sent"] == []

    def test_confirm_sends_and_completes_on_verified_receipt(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()
        state["verify_outcome"] = "sent"

        rc = _run(
            [
                "--env-file",
                str(env_path),
                "--db",
                str(db_path),
                "release-retry",
                AIT_HASH,
                "--confirm",
                "--note",
                "ETH-14 recovery",
            ]
        )
        assert rc == 0
        row = get_withdrawal_by_ait_tx_hash(AIT_HASH)
        assert row["status"] == "completed"
        assert row["eth_tx_hash"] != OLD_ETH_TX
        assert row["release_nonce"] == 1
        assert row["retry_count"] == 1
        attempts = get_release_attempts(AIT_HASH)
        assert len(attempts) == 1
        assert attempts[0]["outcome"] == "sent"
        assert attempts[0]["operator_note"] == "ETH-14 recovery"
        assert attempts[0]["resolved_by"]
        assert len(state["sent"]) == 1
        # The resend carried the estimated gas (207,391 x 1.25), not 100k.
        import rlp

        decoded = rlp.decode(bytes.fromhex(state["sent"][0][2:]))
        assert int.from_bytes(decoded[2], "big") == 259_239

    def test_confirm_refused_without_note(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH, "--confirm"])
        assert rc == 2
        assert state["sent"] == []

    def test_confirm_refused_without_release_env(self, admin_env):
        """--confirm on a host without the bridge release env refuses — the
        live step can only run where BRIDGE_ENABLED + the release key are
        loaded (hub)."""
        state, _, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()
        no_bridge_env = Path(str(db_path)).parent / "ops-nobridge.env"
        no_bridge_env.write_text(
            f"ETH_RPC_URL={RPC_A}\n"
            f"ETH_VERIFY_RPC_URL={RPC_B}\n"
            f"ETH_WALLET_ADDRESS={TEST_ETH_ADDRESS}\n"
            f"ETH_WALLET_PRIVATE_KEY={TEST_ETH_PRIVATE_KEY}\n"
            "BRIDGE_ENABLED=false\n"
            "BLOCKCHAIN_RPC_URL=http://chain.test\n"
        )

        rc = _run(
            [
                "--env-file",
                str(no_bridge_env),
                "--db",
                str(db_path),
                "release-retry",
                AIT_HASH,
                "--confirm",
                "--note",
                "ETH-14 recovery",
            ]
        )
        assert rc == 1
        assert state["sent"] == []
        # Refusal happened before any write — no attempt recorded.
        assert get_release_attempts(AIT_HASH) == []
        assert get_withdrawal_by_ait_tx_hash(AIT_HASH)["retry_count"] == 0

    def test_retry_revert_parks_needs_review_release(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()
        state["verify_outcome"] = "not_sent"

        rc = _run(
            [
                "--env-file",
                str(env_path),
                "--db",
                str(db_path),
                "release-retry",
                AIT_HASH,
                "--confirm",
                "--note",
                "ETH-14 recovery",
            ]
        )
        assert rc == 1
        row = get_withdrawal_by_ait_tx_hash(AIT_HASH)
        assert row["status"] == "needs_review_release"
        attempts = get_release_attempts(AIT_HASH)
        assert attempts[0]["outcome"] == "not_sent"

    def test_second_retry_proven_never_mined_reuses_nonce(self, admin_env):
        """A needs_review_release row may retry again — the recorded retry
        hash absent and its nonce free means the new send reuses that nonce
        (a still-floating earlier blob can never double-pay)."""
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()
        state["verify_outcome"] = "not_sent"

        rc = _run(
            ["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH, "--confirm", "--note", "retry 1"]
        )
        assert rc == 1
        row = get_withdrawal_by_ait_tx_hash(AIT_HASH)
        assert row["status"] == "needs_review_release"
        assert row["release_nonce"] == 1

        # Second run: prove the retry tx never landed — hash absent, nonce 1
        # still free on both endpoints.
        state["rpc"][RPC_A] = _never_mined_rpc(latest_nonce=1)
        state["rpc"][RPC_B] = _never_mined_rpc(latest_nonce=1)
        state["verify_outcome"] = "sent"

        rc = _run(
            ["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH, "--confirm", "--note", "retry 2"]
        )
        assert rc == 0
        row = get_withdrawal_by_ait_tx_hash(AIT_HASH)
        assert row["status"] == "completed"
        assert row["release_nonce"] == 1  # same slot — no nonce was skipped
        assert row["retry_count"] == 2
        assert len(get_release_attempts(AIT_HASH)) == 2
        assert len(state["sent"]) == 2

    def test_second_retry_refused_while_first_unproven(self, admin_env):
        """A still-'releasing_retry' row is machine-owned — refused."""
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()
        state["verify_outcome"] = "unknown"  # stays releasing_retry

        rc = _run(
            ["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH, "--confirm", "--note", "retry 1"]
        )
        assert rc == 0
        row = get_withdrawal_by_ait_tx_hash(AIT_HASH)
        assert row["status"] == "releasing_retry"
        assert len(state["sent"]) == 1

        rc = _run(
            ["--env-file", str(env_path), "--db", str(db_path), "release-retry", AIT_HASH, "--confirm", "--note", "retry 2"]
        )
        assert rc == 1
        assert len(state["sent"]) == 1


class TestMarkReview:
    def test_mark_review_flips_completed_row(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()

        rc = _run(
            [
                "--env-file",
                str(env_path),
                "--db",
                str(db_path),
                "mark-review",
                AIT_HASH,
                "--confirm",
                "--note",
                "ETH-14 refund path",
            ]
        )
        assert rc == 0
        row = get_withdrawal_by_ait_tx_hash(AIT_HASH)
        assert row["status"] == "needs_review"
        assert "ETH-14 refund path" in (row["error"] or "")

    def test_mark_review_dry_run_no_write(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        state["rpc"][RPC_A] = _reverted_rpc()
        state["rpc"][RPC_B] = _reverted_rpc()

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "mark-review", AIT_HASH, "--note", "ETH-14 refund path"])
        assert rc == 0
        assert get_withdrawal_by_ait_tx_hash(AIT_HASH)["status"] == "completed"

    def test_mark_review_requires_note(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "mark-review", AIT_HASH, "--confirm"])
        assert rc == 2

    def test_mark_review_refuses_sent_release(self, admin_env):
        state, env_path, db_path = admin_env
        _seed_completed_row()
        sent = _reverted_rpc()
        sent["eth_getTransactionReceipt"] = {OLD_ETH_TX: {"status": "0x1", "blockNumber": hex(0xB5C122)}}
        state["rpc"][RPC_A] = sent
        state["rpc"][RPC_B] = sent

        rc = _run(["--env-file", str(env_path), "--db", str(db_path), "mark-review", AIT_HASH, "--confirm", "--note", "x"])
        assert rc == 1
        assert get_withdrawal_by_ait_tx_hash(AIT_HASH)["status"] == "completed"
