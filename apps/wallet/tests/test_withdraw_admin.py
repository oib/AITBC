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

import httpx
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
# Obviously fake keyed gateway URLs (ETH-15) — the key path must never
# reach stdout, stderr, an exception, or a stored field.
KEYED_RPC_A = "https://rpc-a.test/v3/FAKEKEY123A"
KEYED_RPC_B = "https://rpc-b.test/v3/FAKEKEY123B"
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


def _keyed_env(env_dir: Path) -> Path:
    """An ops env file whose RPC URLs carry fake key paths (ETH-15)."""
    env = env_dir / "ops-keyed.env"
    env.write_text(
        f"ETH_RPC_URL={KEYED_RPC_A}\n"
        f"ETH_VERIFY_RPC_URL={KEYED_RPC_B}\n"
        f"ETH_WALLET_ADDRESS={TEST_ETH_ADDRESS}\n"
        f"ETH_WALLET_PRIVATE_KEY={TEST_ETH_PRIVATE_KEY}\n"
        "BRIDGE_ENABLED=true\n"
        "BLOCKCHAIN_RPC_URL=http://chain.test\n"
    )
    return env


def _keyed_state(state: dict) -> None:
    """Point the stubbed endpoints at the keyed URLs, both proving reverted."""
    state["rpc"][KEYED_RPC_A] = _reverted_rpc()
    state["rpc"][KEYED_RPC_B] = _reverted_rpc()


def _assert_no_key_leak(capsys) -> None:
    captured = capsys.readouterr()
    for key in ("FAKEKEY123A", "FAKEKEY123B", "/v3/"):
        assert key not in captured.out, f"{key} leaked to stdout"
        assert key not in captured.err, f"{key} leaked to stderr"


class TestKeyedUrlNeverPrinted:
    """ETH-15: a keyed RPC URL must never appear in command output — every
    endpoint is printed as scheme://host only, including on error paths."""

    def test_status(self, admin_env, capsys, tmp_path):
        state, _, db_path = admin_env
        _seed_completed_row()
        _keyed_state(state)
        env = _keyed_env(tmp_path)

        rc = _run(["--env-file", str(env), "--db", str(db_path), "status", AIT_HASH])
        assert rc == 0
        out = capsys.readouterr().out
        assert "https://rpc-a.test" in out  # host still shown
        _assert_no_key_leak(capsys)

    def test_release_retry_dry_run(self, admin_env, capsys, tmp_path):
        state, _, db_path = admin_env
        _seed_completed_row()
        _keyed_state(state)
        env = _keyed_env(tmp_path)

        rc = _run(["--env-file", str(env), "--db", str(db_path), "release-retry", AIT_HASH])
        assert rc == 0
        _assert_no_key_leak(capsys)

    def test_release_retry_confirm(self, admin_env, capsys, tmp_path):
        state, _, db_path = admin_env
        _seed_completed_row()
        _keyed_state(state)
        state["verify_outcome"] = "sent"
        env = _keyed_env(tmp_path)

        rc = _run(
            ["--env-file", str(env), "--db", str(db_path), "release-retry", AIT_HASH, "--confirm", "--note", "ETH-14 retry"]
        )
        assert rc == 0
        _assert_no_key_leak(capsys)

    def test_mark_review(self, admin_env, capsys, tmp_path):
        state, _, db_path = admin_env
        _seed_completed_row()
        _keyed_state(state)
        env = _keyed_env(tmp_path)

        rc = _run(
            ["--env-file", str(env), "--db", str(db_path), "mark-review", AIT_HASH, "--confirm", "--note", "refund path"]
        )
        assert rc == 0
        _assert_no_key_leak(capsys)

    def test_rpc_error_path(self, admin_env, capsys, tmp_path, monkeypatch):
        """An endpoint that errors still prints only its host — including
        when the exception text itself carried the keyed URL."""
        import wallet_app.bridge.withdraw_admin as admin

        state, _, db_path = admin_env
        _seed_completed_row()
        env = _keyed_env(tmp_path)

        async def _raise_keyed(url: str, method: str, params: list):
            raise RuntimeError(f"{method} request to {url} failed: connection refused")

        monkeypatch.setattr(admin, "_rpc_call", _raise_keyed)
        rc = _run(["--env-file", str(env), "--db", str(db_path), "status", AIT_HASH])
        assert rc == 0
        out = capsys.readouterr().out
        assert "rpc error" in out
        _assert_no_key_leak(capsys)

    def test_broadcast_failure_never_stores_keyed_url(self, admin_env, capsys, tmp_path, monkeypatch):
        """The attempt row's outcome field is persisted — it must carry
        the redacted exception text too."""
        import wallet_app.bridge.bridge_withdraw_monitor as wdm

        state, _, db_path = admin_env
        _seed_completed_row()
        _keyed_state(state)
        env = _keyed_env(tmp_path)

        async def _broadcast_fails(raw: str) -> str:
            raise RuntimeError(f"send to {KEYED_RPC_A} timed out")

        monkeypatch.setattr(wdm, "_broadcast_release_tx", _broadcast_fails)
        rc = _run(
            ["--env-file", str(env), "--db", str(db_path), "release-retry", AIT_HASH, "--confirm", "--note", "ETH-14 retry"]
        )
        assert rc == 1
        _assert_no_key_leak(capsys)
        attempts = get_release_attempts(AIT_HASH)
        assert len(attempts) == 1
        assert "FAKEKEY123A" not in (attempts[0]["outcome"] or "")
        assert "https://rpc-a.test" in attempts[0]["outcome"]


class TestRpcCallRedaction:
    """_rpc_call wraps httpx so an HTTP error never raises text carrying
    the endpoint URL (httpx embeds it in the exception message)."""

    class _Client:
        """AsyncContextManager double returning a canned response."""

        def __init__(self, response):
            self._response = response

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None):
            return self._response

    def test_http_status_error_is_redacted(self, monkeypatch):
        import wallet_app.bridge.withdraw_admin as admin

        request = httpx.Request("POST", KEYED_RPC_A)
        response = httpx.Response(503, request=request)
        client = self._Client(response)
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

        with pytest.raises(RuntimeError) as exc:
            asyncio.run(admin._rpc_call(KEYED_RPC_A, "eth_getBalance", ["0x0", "latest"]))
        msg = str(exc.value)
        assert "FAKEKEY123A" not in msg
        assert "/v3/" not in msg
        assert "https://rpc-a.test" in msg

    def test_json_rpc_error_is_redacted(self, monkeypatch):
        import wallet_app.bridge.withdraw_admin as admin

        request = httpx.Request("POST", KEYED_RPC_A)
        response = httpx.Response(
            200,
            json={"error": {"code": -32000, "message": "historical state is not available"}},
            request=request,
        )
        client = self._Client(response)
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)

        with pytest.raises(RuntimeError) as exc:
            asyncio.run(admin._rpc_call(KEYED_RPC_A, "eth_getBalance", ["0x0", "latest"]))
        msg = str(exc.value)
        assert "FAKEKEY123A" not in msg
        assert "https://rpc-a.test" in msg
        assert "historical state is not available" in msg


class TestUrlRedact:
    def test_redact_url_drops_path_query_userinfo(self):
        from wallet_app.bridge.url_redact import redact_url

        assert redact_url("https://user:pw@rpc-a.test/v3/KEY?q=1#f") == "https://rpc-a.test"
        assert redact_url("http://127.0.0.1:8202/rpc/transaction") == "http://127.0.0.1:8202"
        assert redact_url(KEYED_RPC_A) == "https://rpc-a.test"

    def test_redact_url_never_echoes_bad_input(self):
        from wallet_app.bridge.url_redact import redact_url

        assert redact_url("") == "(unset)"
        assert redact_url(None) == "(unset)"
        assert redact_url("KEYMATERIAL without scheme") == "(redacted)"

    def test_redact_text_replaces_urls_in_sentence(self):
        from wallet_app.bridge.url_redact import redact_text

        out = redact_text(f"Client error '404' for url '{KEYED_RPC_A}'. retry later")
        assert "FAKEKEY123A" not in out
        assert "https://rpc-a.test'." in out


class TestEnvFilePrecedence:
    """_load_env_files is last-file-wins between the files (systemd
    EnvironmentFile semantics), while an already-exported shell variable
    still wins over every file (ETH-15)."""

    def test_later_file_overrides_earlier(self, tmp_path, monkeypatch):
        import wallet_app.bridge.withdraw_admin as admin

        first = tmp_path / "first.env"
        first.write_text("ETH15_VAR=first\nETH15_KEEP=keep\n")
        second = tmp_path / "second.env"
        second.write_text("ETH15_VAR=second\n")
        monkeypatch.delenv("ETH15_VAR", raising=False)
        monkeypatch.delenv("ETH15_KEEP", raising=False)

        admin._load_env_files([str(first), str(second)])
        assert os.environ["ETH15_VAR"] == "second"
        assert os.environ["ETH15_KEEP"] == "keep"

    def test_exported_variable_still_wins(self, tmp_path, monkeypatch):
        import wallet_app.bridge.withdraw_admin as admin

        env_file = tmp_path / "one.env"
        env_file.write_text("ETH15_VAR=file\n")
        monkeypatch.setenv("ETH15_VAR", "exported")

        admin._load_env_files([str(env_file)])
        assert os.environ["ETH15_VAR"] == "exported"
