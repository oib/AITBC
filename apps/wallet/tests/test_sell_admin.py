"""sell_admin CLI tests (ETH-13) — every verb, refusal path, audit columns."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from aitbc.utils import ait_to_units
from wallet_app.bridge import sell_admin as admin
from wallet_app.bridge import sell_escrow_monitor as sellmon
from wallet_app.bridge.bridge_db import (
    get_sell_eth_committed_since,
    get_sell_lock_by_ait_tx_hash,
    get_sell_pending_eth_reserve,
    init_db,
    insert_sell_lock,
    insert_sell_quote,
    update_sell_lock_status,
)

TEST_ESCROW_KEY = "0x" + "22" * 32
TEST_TREASURY = "0x3333333333333333333333333333333333333333"
SHOP_AIT = "0x4444444444444444444444444444444444444444"
SHOP_ETH = "0x5555555555555555555555555555555555555555"
LOCK_HASH = "0x" + "ab" * 32
SEALED_HASH = "0x" + "77" * 32
_SIG = "de" * 65


def _escrow_address() -> str:
    from eth_keys import keys as eth_keys

    return eth_keys.PrivateKey(bytes.fromhex("22" * 32)).public_key.to_checksum_address()


@pytest.fixture
def admin_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """sell_admin environment: tmp DB + empty env file (keeps real
    /etc/aitbc files out), sell config env vars set, chain seams stubbed."""
    db_path = tmp_path / "bridge.db"
    escrow = _escrow_address()
    wallet_file = tmp_path / "escrow.json"
    wallet_file.write_text(json.dumps({"address": escrow, "private_key": TEST_ESCROW_KEY}))
    env_file = tmp_path / "ops.env"
    env_file.write_text("# test env — nothing to load\n")

    for key in (
        "AIT_SELL_ESCROW",
        "SELL_ESCROW_WALLET_PATH",
        "SELL_ESCROW_CREDENTIAL_FILE",
        "SELL_TREASURY_ADDRESS",
        "CHAIN_ID",
        "BLOCKCHAIN_RPC_URL",
        "CREDENTIALS_DIRECTORY",
        "SELL_ESCROW_ENABLED",
        "BLOCKCHAIN_MODE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BLOCKCHAIN_MODE", "hub")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setenv("AIT_SELL_ESCROW", escrow)
    monkeypatch.setenv("SELL_ESCROW_WALLET_PATH", str(wallet_file))
    monkeypatch.setenv("SELL_TREASURY_ADDRESS", TEST_TREASURY)
    monkeypatch.setenv("CHAIN_ID", "ait-testnet")
    monkeypatch.setenv("BLOCKCHAIN_RPC_URL", "http://localhost:0")

    state: dict[str, Any] = {
        "escrow_nonce": 0,
        "escrow_balance": Decimal("1000"),
        "transfers": [],
        "ait_sends": [],
    }

    async def _account_view(address: str) -> tuple[int, Decimal]:
        return int(state["escrow_nonce"]), Decimal(str(state["escrow_balance"]))

    async def _transfers(address: str, limit: int = 0) -> list[dict]:
        return list(state["transfers"])

    async def _broadcast(tx: dict) -> str:
        state["ait_sends"].append(tx)
        return "0x" + "ff" * 32

    monkeypatch.setattr(sellmon, "_account_view", _account_view)
    monkeypatch.setattr(sellmon, "_fetch_transfers", _transfers)
    monkeypatch.setattr(sellmon, "_broadcast_ait_tx", _broadcast)
    monkeypatch.setattr(sellmon, "_db_initialized", False)

    with patch("wallet_app.bridge.bridge_db.DB_PATH", str(db_path)):
        init_db()
        state["escrow"] = escrow
        state["db_path"] = db_path
        state["env_file"] = env_file
        yield state


def _run(state: dict, argv: list[str]) -> int:
    return admin.main(["--env-file", str(state["env_file"]), "--db", str(state["db_path"]), *argv])


def _insert_quote(ait_amount: Decimal = Decimal("10")) -> str:
    fee_ait = (ait_amount * Decimal("0.005")).quantize(Decimal("0.000001"))
    net_ait = ait_amount - fee_ait
    eth_amount = (net_ait * Decimal("0.28") / Decimal("3000")).quantize(Decimal("0.00000001"))
    return insert_sell_quote(
        shop_ait_address=SHOP_AIT,
        shop_eth_address=SHOP_ETH,
        ait_amount=ait_amount,
        rate_eth_usd=Decimal("3000"),
        ait_usd=Decimal("0.28"),
        fee_ait=fee_ait,
        eth_amount=eth_amount,
        expires_at=(datetime.now() + timedelta(seconds=900)).isoformat(),
    )


def _intent_blob(ait_tx_hash: str, *, lane: str = "settle", nonce: int = 5, ait: Decimal = Decimal("10")) -> str:
    """A persisted sweep intent as _escrow_sweep writes it (blob shape only)."""
    to = TEST_TREASURY if lane == "settle" else SHOP_AIT
    reason = "sell_settle" if lane == "settle" else "release never reached the chain"
    return json.dumps(
        {
            "type": "TRANSFER",
            "chain_id": "ait-testnet",
            "from": _escrow_address(),
            "to": to,
            "amount": ait_to_units(ait),
            "fee": ait_to_units(Decimal("0.01")),
            "nonce": nonce,
            "payload": {"amount": ait_to_units(ait), "sell_ref": ait_tx_hash, "reason": reason},
            "signature": _SIG,
        }
    )


def _seed_lock(
    status: str,
    *,
    tx: str = LOCK_HASH,
    ait: Decimal = Decimal("10"),
    eth: Decimal | None = None,
    nonce: int | None = None,
    blob: str | None = None,
    with_quote: bool = False,
    error: str | None = None,
) -> str:
    quote_id = _insert_quote(ait) if with_quote else None
    insert_sell_lock(
        ait_tx_hash=tx,
        shop_ait_address=SHOP_AIT,
        shop_eth_address=SHOP_ETH,
        amount_ait=ait,
        eth_amount=eth,
        quote_id=quote_id,
        status=status,
        locked_height=900,
        error=error,
    )
    extras: dict[str, Any] = {}
    if nonce is not None:
        extras["escrow_out_nonce"] = nonce
    if blob is not None:
        extras["escrow_out_tx"] = blob
    if extras:
        update_sell_lock_status(tx, status, **extras)
    return tx


def _sealed_sweep_tx(
    sell_ref: str,
    to: str,
    ait: Decimal,
    nonce: int,
    tx_hash: str = SEALED_HASH,
) -> dict:
    """A sealed escrow outbound TRANSFER — the shape _find_escrow_outflow matches."""
    return {
        "tx_hash": tx_hash,
        "sender": _escrow_address(),
        "recipient": to,
        "value": ait_to_units(ait),
        "payload": {"amount": ait_to_units(ait), "sell_ref": sell_ref, "reason": "x"},
        "block_height": 950,
        "nonce": nonce,
        "status": "confirmed",
        "type": "TRANSFER",
    }


def _sweep_review_lock(lane: str = "settle", nonce: int = 5, **kw: Any) -> str:
    """A needs_review_sweep row holding a persisted settle/refund intent."""
    tx = kw.pop("tx", LOCK_HASH)
    return _seed_lock(
        "needs_review_sweep",
        tx=tx,
        nonce=nonce,
        blob=_intent_blob(tx, lane=lane, nonce=nonce),
        error="escrow nonce 5 consumed by an unmatched transaction",
        **kw,
    )


class TestHostGates:
    """Root-on-hub-only + ledger-presence refusals (decided 14 Oct)."""

    def test_refuse_non_root(self, admin_env, monkeypatch, capsys):
        monkeypatch.setattr(os, "geteuid", lambda: 1000)
        assert _run(admin_env, ["list"]) == 2
        assert "as root" in capsys.readouterr().out

    def test_refuse_non_hub(self, admin_env, monkeypatch, capsys):
        monkeypatch.setenv("BLOCKCHAIN_MODE", "follower")
        assert _run(admin_env, ["list"]) == 2
        assert "hub" in capsys.readouterr().out

    def test_refuse_missing_default_db(self, admin_env, monkeypatch, capsys, tmp_path):
        """Without the ledger the command refuses — it must not let
        init_db create an empty DB on a host that never had one."""
        missing = tmp_path / "absent" / "bridge.db"
        monkeypatch.setattr("wallet_app.bridge.bridge_db.DB_PATH", str(missing))
        rc = admin.main(["--env-file", str(admin_env["env_file"]), "list"])
        assert rc == 2
        assert "ledger" in capsys.readouterr().out
        assert not missing.exists()

    def test_refuse_missing_db_arg(self, admin_env, capsys, tmp_path):
        rc = _run(admin_env, ["--db", str(tmp_path / "gone.db"), "list"])
        assert rc == 2
        assert "ledger" in capsys.readouterr().out


class TestStatus:
    """CLI-5: `status` prints sell_config_status + non-secret config — the
    sell lane's state readable without journald (env-only verb)."""

    def test_disabled_state(self, admin_env, capsys):
        rc = _run(admin_env, ["status"])
        assert rc == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["enabled"] is False
        assert doc["reason"] == "sell escrow disabled"
        assert doc["flags"]["sell_escrow_enabled"] is False
        # Config parses independently of the feature flag — addresses and
        # limits still show so the operator can see what enabling would use.
        assert doc["config"]["escrow_address"]
        assert doc["config"]["chain_id"] == "ait-testnet"
        assert doc["config"]["escrow_wallet_configured"] is True
        # No key-slot path or credential name leaks into the doc.
        assert str(admin_env["db_path"]) not in json.dumps(doc)
        for secret_key in ("escrow_wallet_path", "escrow_credential_file", "escrow_credential_name", "private_key"):
            assert secret_key not in doc["config"]

    def test_enabled_state(self, admin_env, capsys, monkeypatch):
        monkeypatch.setenv("SELL_ESCROW_ENABLED", "true")
        monkeypatch.setenv("BRIDGE_ENABLED", "true")
        rc = _run(admin_env, ["status"])
        assert rc == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["enabled"] is True
        assert doc["reason"] == ""
        assert doc["feature_enabled"] is True

    def test_bridge_off_reports_reason(self, admin_env, capsys, monkeypatch):
        monkeypatch.setenv("SELL_ESCROW_ENABLED", "true")
        rc = _run(admin_env, ["status"])
        assert rc == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["enabled"] is False
        assert doc["reason"] == "bridge disabled"

    def test_status_runs_without_ledger(self, admin_env, capsys, tmp_path, monkeypatch):
        """The env-only verb bypasses the ledger gate — status must still
        answer when the DB does not exist."""
        missing = tmp_path / "no-such-dir" / "bridge.db"
        rc = admin.main(["--env-file", str(admin_env["env_file"]), "--db", str(missing), "status"])
        assert rc == 0
        assert "enabled" in capsys.readouterr().out

    def test_status_still_gated(self, admin_env, capsys, monkeypatch):
        monkeypatch.setattr(os, "geteuid", lambda: 1000)
        rc = _run(admin_env, ["status"])
        assert rc == 2
        assert "root" in capsys.readouterr().out


class TestList:
    def test_lists_open_rows(self, admin_env):
        _seed_lock("locked", tx=LOCK_HASH)
        _seed_lock("settled", tx="0x" + "cd" * 32)
        rc = _run(admin_env, ["list"])
        assert rc == 0

    def test_open_filter_hides_terminal(self, admin_env, capsys):
        _seed_lock("locked", tx=LOCK_HASH)
        _seed_lock("settled", tx="0x" + "cd" * 32)
        _run(admin_env, ["list"])
        out = capsys.readouterr().out
        assert LOCK_HASH in out
        assert "cd" * 32 not in out
        assert "1 row(s)" in out

    def test_status_filter(self, admin_env, capsys):
        _sweep_review_lock()
        _run(admin_env, ["list", "--status", "needs_review_sweep"])
        assert LOCK_HASH in capsys.readouterr().out

    def test_status_filter_no_match(self, admin_env, capsys):
        _seed_lock("locked", tx=LOCK_HASH)
        rc = _run(admin_env, ["list", "--status", "needs_review_sweep"])
        assert rc == 0
        assert "no sell locks match" in capsys.readouterr().out


class TestInspect:
    def test_unknown_hash(self, admin_env, capsys):
        assert _run(admin_env, ["inspect", "0xdead"]) == 1
        assert "no sell lock" in capsys.readouterr().out

    def test_full_view_without_blob(self, admin_env, capsys):
        _sweep_review_lock(with_quote=True)
        assert _run(admin_env, ["inspect", LOCK_HASH]) == 0
        out = capsys.readouterr().out
        assert "needs_review_sweep" in out
        assert "escrow_out_nonce: 5" in out
        assert "sell_ref" in out  # parsed intent payload
        assert "sweep lane: settle" in out
        assert "nonce=0" in out and "balance=1000" in out  # escrow chain view
        # The signed blob and its signature must never print.
        assert _SIG not in out
        assert '"signature"' not in out.replace("<present>", "")

    def test_quote_shown(self, admin_env, capsys):
        _sweep_review_lock(with_quote=True)
        _run(admin_env, ["inspect", LOCK_HASH])
        out = capsys.readouterr().out
        assert "quote:" in out and "rate_eth_usd" in out


class TestConfirmSwept:
    def test_dry_run_writes_nothing(self, admin_env, capsys):
        _sweep_review_lock()
        admin_env["transfers"] = [_sealed_sweep_tx(LOCK_HASH, TEST_TREASURY, Decimal("10"), 5)]
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH])
        assert rc == 0
        assert "dry-run" in capsys.readouterr().out
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "needs_review_sweep"

    def test_confirm_settles_with_audit(self, admin_env, capsys):
        _sweep_review_lock()
        admin_env["transfers"] = [_sealed_sweep_tx(LOCK_HASH, TEST_TREASURY, Decimal("10"), 5)]
        rc = _run(
            admin_env,
            ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH, "--confirm", "--note", "manual check", "--operator", "opsbot"],
        )
        assert rc == 0
        row = get_sell_lock_by_ait_tx_hash(LOCK_HASH)
        assert row["status"] == "settled"
        assert row["settle_tx_hash"] == SEALED_HASH
        assert row["resolved_by"] == "opsbot"
        assert row["resolved_at"]
        assert row["operator_note"] == "manual check"
        assert "operator:confirm-swept" in row["error"]
        assert row["settled_at"]

    def test_confirm_refund_lane(self, admin_env):
        _sweep_review_lock(lane="refund")
        admin_env["transfers"] = [_sealed_sweep_tx(LOCK_HASH, SHOP_AIT, Decimal("10"), 5)]
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH, "--confirm", "--note", "refund sealed"])
        assert rc == 0
        row = get_sell_lock_by_ait_tx_hash(LOCK_HASH)
        assert row["status"] == "refunded"
        assert row["refund_tx_hash"] == SEALED_HASH

    def test_missing_blob_lane_from_outflow(self, admin_env):
        """Blob gone but nonce recorded — the sealed outflow's recipient decides the lane."""
        _seed_lock("needs_review_sweep", nonce=5, blob=None)
        admin_env["transfers"] = [_sealed_sweep_tx(LOCK_HASH, TEST_TREASURY, Decimal("10"), 5)]
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH, "--confirm", "--note", "n"])
        assert rc == 0
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "settled"

    def test_refuse_wrong_status(self, admin_env, capsys):
        _seed_lock("released")
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert "not operator-gated" in capsys.readouterr().out

    def test_needs_review_not_matched(self, admin_env, capsys):
        """Plain needs_review (release path) is machine-owned — never operator-resolved here."""
        _seed_lock("needs_review")
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "needs_review"

    def test_refuse_hash_mismatch(self, admin_env, capsys):
        """The sealed outflow exists but the supplied --tx names a different hash."""
        _sweep_review_lock()
        admin_env["transfers"] = [_sealed_sweep_tx(LOCK_HASH, TEST_TREASURY, Decimal("10"), 5)]
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", "0x" + "99" * 32, "--confirm", "--note", "n"])
        assert rc == 1
        assert "does not equal" in capsys.readouterr().out
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "needs_review_sweep"

    def test_refuse_already_settled(self, admin_env, capsys):
        """Double-sweep guard: a settled row is terminal — confirm-swept
        must refuse it even with a valid-looking hash."""
        _seed_lock("settled")
        admin_env["transfers"] = [_sealed_sweep_tx(LOCK_HASH, TEST_TREASURY, Decimal("10"), 5)]
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert "not operator-gated" in capsys.readouterr().out

    def test_refuse_foreign_nonce_outflow(self, admin_env, capsys):
        """An outflow sealed at a nonce this row never recorded — another
        row's sweep — can never be credited here."""
        _sweep_review_lock(nonce=5)
        foreign = _sealed_sweep_tx(LOCK_HASH, TEST_TREASURY, Decimal("10"), 6, tx_hash=SEALED_HASH)
        admin_env["transfers"] = [foreign]
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert "no sealed escrow outflow" in capsys.readouterr().out
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "needs_review_sweep"

    def test_refuse_sell_ref_mismatch(self, admin_env, capsys):
        """Same nonce+recipient+amount but a different sell_ref — hard refuse."""
        _sweep_review_lock()
        foreign = _sealed_sweep_tx("0x" + "ef" * 32, TEST_TREASURY, Decimal("10"), 5, tx_hash=SEALED_HASH)
        admin_env["transfers"] = [foreign]
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert "no sealed escrow outflow" in capsys.readouterr().out
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "needs_review_sweep"

    def test_refuse_no_nonce(self, admin_env, capsys):
        _seed_lock("needs_review_sweep", blob=_intent_blob(LOCK_HASH))
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH])
        assert rc == 1
        assert "no recorded sweep nonce" in capsys.readouterr().out

    def test_confirm_requires_note(self, admin_env, capsys):
        _sweep_review_lock()
        admin_env["transfers"] = [_sealed_sweep_tx(LOCK_HASH, TEST_TREASURY, Decimal("10"), 5)]
        rc = _run(admin_env, ["confirm-swept", LOCK_HASH, "--tx", SEALED_HASH, "--confirm"])
        assert rc == 2
        assert "requires --note" in capsys.readouterr().out

    def test_tx_flag_required(self, admin_env):
        _sweep_review_lock()
        with pytest.raises(SystemExit):
            _run(admin_env, ["confirm-swept", LOCK_HASH])


class TestRequeue:
    def test_dry_run(self, admin_env, capsys):
        _sweep_review_lock()
        rc = _run(admin_env, ["requeue", LOCK_HASH])
        assert rc == 0
        assert "status=released" in capsys.readouterr().out
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "needs_review_sweep"

    def test_settle_lane_requeues_to_released(self, admin_env):
        _sweep_review_lock()
        rc = _run(admin_env, ["requeue", LOCK_HASH, "--confirm", "--note", "foreign tx was a funding top-up"])
        assert rc == 0
        row = get_sell_lock_by_ait_tx_hash(LOCK_HASH)
        assert row["status"] == "released"
        assert row["resolved_by"]
        assert row["operator_note"] == "foreign tx was a funding top-up"
        assert "operator:requeue" in row["error"]

    def test_refund_lane_requeues_to_refund_pending(self, admin_env):
        _sweep_review_lock(lane="refund")
        rc = _run(admin_env, ["requeue", LOCK_HASH, "--confirm", "--note", "n"])
        assert rc == 0
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "refund_pending"

    def test_refuse_while_sweep_in_flight(self, admin_env, capsys):
        _sweep_review_lock()
        _seed_lock("settling", tx="0x" + "cd" * 32, nonce=6, blob=_intent_blob("0x" + "cd" * 32, nonce=6))
        rc = _run(admin_env, ["requeue", LOCK_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert "already in flight" in capsys.readouterr().out
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "needs_review_sweep"

    def test_refuse_unreadable_intent(self, admin_env, capsys):
        """Blob missing entirely — the lane cannot be derived; refuse."""
        _seed_lock("needs_review_sweep", nonce=5)
        rc = _run(admin_env, ["requeue", LOCK_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert "cannot tell which lane" in capsys.readouterr().out

    def test_refuse_needs_review(self, admin_env, capsys):
        _seed_lock("needs_review")
        rc = _run(admin_env, ["requeue", LOCK_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert "not operator-gated" in capsys.readouterr().out

    def test_requeued_row_sweeps_once_under_monitor(self, admin_env):
        """Serialization across a manual requeue: the monitor's own sweep
        path sends exactly once and its in-flight gate defers a concurrent
        sweep — a requeued row can never be swept twice."""
        _sweep_review_lock()
        assert _run(admin_env, ["requeue", LOCK_HASH, "--confirm", "--note", "n"]) == 0
        row = get_sell_lock_by_ait_tx_hash(LOCK_HASH)
        assert row["status"] == "released"

        cfg = sellmon._sell_config()
        outcome = asyncio.run(
            sellmon._escrow_sweep(cfg, row, cfg.treasury_address, "sell_settle", "settling", "queued_fee_settle")
        )
        assert outcome == "sent"
        assert len(admin_env["ait_sends"]) == 1
        in_flight = get_sell_lock_by_ait_tx_hash(LOCK_HASH)
        assert in_flight["status"] == "settling"

        second = asyncio.run(
            sellmon._escrow_sweep(cfg, in_flight, cfg.treasury_address, "sell_settle", "settling", "queued_fee_settle")
        )
        assert second == "deferred"
        assert len(admin_env["ait_sends"]) == 1


class TestWriteOff:
    def test_dry_run(self, admin_env, capsys):
        _sweep_review_lock()
        rc = _run(admin_env, ["write-off", LOCK_HASH, "--reason", "nonce burned by manual send"])
        assert rc == 0
        assert "dry-run" in capsys.readouterr().out
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "needs_review_sweep"

    def test_confirm_writes_terminal(self, admin_env):
        _sweep_review_lock()
        rc = _run(
            admin_env,
            ["write-off", LOCK_HASH, "--reason", "nonce burned", "--confirm", "--note", "op decision", "--operator", "opsbot"],
        )
        assert rc == 0
        row = get_sell_lock_by_ait_tx_hash(LOCK_HASH)
        assert row["status"] == "written_off"
        assert "operator:write-off nonce burned" in row["error"]
        assert row["resolved_by"] == "opsbot"
        assert row["operator_note"] == "op decision"

    def test_reason_required(self, admin_env):
        _sweep_review_lock()
        with pytest.raises(SystemExit):
            _run(admin_env, ["write-off", LOCK_HASH, "--confirm", "--note", "n"])

    def test_refuse_terminal_row(self, admin_env, capsys):
        _seed_lock("settled")
        rc = _run(admin_env, ["write-off", LOCK_HASH, "--reason", "r", "--confirm", "--note", "n"])
        assert rc == 1
        assert "already terminal" in capsys.readouterr().out

    def test_refuse_inflight_send(self, admin_env, capsys):
        """A 'settling' row's blob may still seal — abandoning it strands truth."""
        _seed_lock("settling", nonce=5, blob=_intent_blob(LOCK_HASH))
        rc = _run(admin_env, ["write-off", LOCK_HASH, "--reason", "r", "--confirm", "--note", "n"])
        assert rc == 1
        assert "live send in flight" in capsys.readouterr().out
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "settling"


class TestSweepNow:
    def test_refuse_non_queued(self, admin_env, capsys):
        _sweep_review_lock()
        rc = _run(admin_env, ["sweep-now", LOCK_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert "only accelerates" in capsys.readouterr().out

    def test_refuse_inflight(self, admin_env, capsys):
        _seed_lock("queued_fee_settle", tx=LOCK_HASH)
        _seed_lock("settling", tx="0x" + "cd" * 32, nonce=6, blob=_intent_blob("0x" + "cd" * 32, nonce=6))
        rc = _run(admin_env, ["sweep-now", LOCK_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert "already in flight" in capsys.readouterr().out
        assert admin_env["ait_sends"] == []

    def test_dry_run(self, admin_env, capsys):
        _seed_lock("queued_fee_settle", tx=LOCK_HASH)
        rc = _run(admin_env, ["sweep-now", LOCK_HASH])
        assert rc == 0
        out = capsys.readouterr().out
        assert "planned sweep" in out and "sufficient" in out
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "queued_fee_settle"
        assert admin_env["ait_sends"] == []

    def test_confirm_sends_through_monitor_path(self, admin_env, capsys):
        _seed_lock("queued_fee_settle", tx=LOCK_HASH)
        rc = _run(admin_env, ["sweep-now", LOCK_HASH, "--confirm", "--note", "funded the escrow"])
        assert rc == 0
        row = get_sell_lock_by_ait_tx_hash(LOCK_HASH)
        assert row["status"] == "settling"
        assert row["escrow_out_nonce"] == 0
        assert row["escrow_out_tx"]  # intent persisted before broadcast
        assert len(admin_env["ait_sends"]) == 1
        assert admin_env["ait_sends"][0]["payload"]["sell_ref"] == LOCK_HASH
        assert admin_env["ait_sends"][0]["to"] == TEST_TREASURY
        # The audit pre-write stamped the operator action.
        assert row["operator_note"] == "funded the escrow"
        assert row["resolved_by"]

    def test_confirm_refund_lane(self, admin_env):
        _seed_lock("queued_fee_refund", tx=LOCK_HASH, error="refund; escrow fee float deficit 5 AIT")
        rc = _run(admin_env, ["sweep-now", LOCK_HASH, "--confirm", "--note", "n"])
        assert rc == 0
        assert admin_env["ait_sends"][0]["to"] == SHOP_AIT
        assert admin_env["ait_sends"][0]["payload"]["reason"] == "refund"
        assert get_sell_lock_by_ait_tx_hash(LOCK_HASH)["status"] == "refunding"

    def test_short_float_reparks(self, admin_env, capsys):
        _seed_lock("queued_fee_settle", tx=LOCK_HASH)
        admin_env["escrow_balance"] = Decimal("1")  # amount 10 + 0.01 fee > 1
        rc = _run(admin_env, ["sweep-now", LOCK_HASH, "--confirm", "--note", "n"])
        assert rc == 1
        assert "re-parked" in capsys.readouterr().out
        row = get_sell_lock_by_ait_tx_hash(LOCK_HASH)
        assert row["status"] == "queued_fee_settle"
        assert "escrow fee float deficit" in row["error"]
        assert admin_env["ait_sends"] == []

    def test_confirm_requires_note(self, admin_env, capsys):
        _seed_lock("queued_fee_settle", tx=LOCK_HASH)
        rc = _run(admin_env, ["sweep-now", LOCK_HASH, "--confirm"])
        assert rc == 2
        assert "requires --note" in capsys.readouterr().out


# Pre-ETH-13 shape of bridge_sell_locks — a copy of the deployed schema
# without the audit columns, to prove init_db migrates it in place.
_OLD_LOCKS_DDL = """
    CREATE TABLE bridge_sell_locks (
        id TEXT PRIMARY KEY,
        quote_id TEXT,
        ait_tx_hash TEXT UNIQUE NOT NULL,
        shop_ait_address TEXT NOT NULL,
        shop_eth_address TEXT,
        amount_ait NUMERIC NOT NULL,
        eth_amount NUMERIC,
        requoted INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'locked',
        eth_tx_hash TEXT,
        release_nonce INTEGER,
        settle_tx_hash TEXT,
        refund_tx_hash TEXT,
        escrow_out_nonce INTEGER,
        escrow_out_tx TEXT,
        locked_height INTEGER,
        locked_at TIMESTAMP,
        error TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        released_at TIMESTAMP,
        settled_at TIMESTAMP,
        refunded_at TIMESTAMP
    )
"""


class TestAuditMigration:
    def test_init_db_adds_audit_columns_to_old_schema(self, tmp_path: Path):
        """A DB carrying the pre-ETH-13 schema gains the columns via init_db's
        ALTERs — the same mechanism retry_count/eth_withdrawal_release_attempts
        used."""
        import sqlite3

        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(db_path)
        conn.execute(_OLD_LOCKS_DDL)
        conn.commit()
        conn.close()

        with patch("wallet_app.bridge.bridge_db.DB_PATH", str(db_path)):
            init_db()
            conn = sqlite3.connect(db_path)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(bridge_sell_locks)").fetchall()}
            conn.close()
            assert {"resolved_by", "resolved_at", "operator_note"} <= cols

            # …and rows migrate-through writes work on the upgraded schema.
            insert_sell_lock(
                ait_tx_hash=LOCK_HASH,
                shop_ait_address=SHOP_AIT,
                amount_ait=Decimal("10"),
                status="needs_review_sweep",
            )
            ok = update_sell_lock_status(
                LOCK_HASH,
                "written_off",
                error="operator:write-off test",
                resolved_by="opsbot",
                resolved_at="2026-10-14T12:00:00",
                operator_note="migrated row audit",
            )
            assert ok
            row = get_sell_lock_by_ait_tx_hash(LOCK_HASH)
            assert row["resolved_by"] == "opsbot"
            assert row["operator_note"] == "migrated row audit"


class TestCapAccounting:
    """The decided-14-Oct semantics: a written-off row counts toward the
    daily release cap only when it actually recorded a release tx, and is
    always out of the pending reserve."""

    def test_written_off_with_release_counts(self, admin_env):
        """Release broadcast before the write-off — the ETH may be gone,
        so the spend still counts (same as a settled row)."""
        _seed_lock("written_off", tx=LOCK_HASH, ait=Decimal("10"), eth=Decimal("0.005"))
        update_sell_lock_status(LOCK_HASH, "released", eth_tx_hash="0x" + "dd" * 32, release_nonce=3)
        update_sell_lock_status(LOCK_HASH, "written_off")
        since = (datetime.now() - timedelta(hours=1)).isoformat()
        assert get_sell_eth_committed_since(since) > 0

    def test_written_off_without_release_excluded(self, admin_env):
        """Written off before any release — nothing left the wallet."""
        _seed_lock("written_off", tx=LOCK_HASH, ait=Decimal("10"), eth=Decimal("0.005"))
        since = (datetime.now() - timedelta(hours=1)).isoformat()
        assert get_sell_eth_committed_since(since) == 0

    def test_written_off_out_of_reserve(self, admin_env):
        """The reserve is for ETH not yet paid — an abandoned row frees it."""
        _seed_lock("written_off", tx=LOCK_HASH, ait=Decimal("10"), eth=Decimal("0.005"))
        assert get_sell_pending_eth_reserve() == 0
