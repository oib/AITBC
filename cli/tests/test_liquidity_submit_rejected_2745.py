"""#2745 pins: ``_submit_liquidity_transaction`` must not echo a dead hash.

The tx hash is content-deterministic — resubmitting a transaction the chain
already rejected rebuilds the identical hash. The node reports a live pending
resubmission ahead of the stale rejected row, so a bare ``status="rejected"``
answer means this exact transaction is dead: the submit path fails loudly
instead of letting ``liquidity-unstake`` mark the stake completed and print
the corpse hash as if it had been submitted.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip("click", reason="cli dependencies not installed")
pytest.importorskip("eth_keys", reason="wallet signing needs eth-keys")

import click  # noqa: E402

from aitbc_cli.commands.wallet import staking as wallet_staking  # noqa: E402

TX_HASH = "0x" + "e1" * 32
ADDRESS = "0x" + "11" * 20


def _ctx() -> click.Context:
    ctx = click.Context(click.Command("test"))
    ctx.obj = {"rpc_url": "http://rpc.test", "chain_id_explicit": "test-chain"}
    return ctx


def _wallet_data() -> dict:
    return {"address": ADDRESS, "private_key": "a" * 64}


def _client(monkeypatch, status_record: dict | None = None, status_exc: Exception | None = None):
    client = Mock()
    client.post.return_value = {"transaction_hash": TX_HASH}

    def _get(path: str):
        if "/rpc/transaction/" in path:
            if status_exc is not None:
                raise status_exc
            return status_record or {}
        if "/rpc/account/" in path:
            return {"nonce": 0}
        return {}

    client.get.side_effect = _get
    monkeypatch.setattr(wallet_staking, "AITBCHTTPClient", lambda *a, **k: client)
    return client


def _tx() -> dict:
    return {
        "type": "LIQUIDITY_WITHDRAW",
        "from": ADDRESS,
        "to": ADDRESS,
        "amount": 0,
        "fee": 1,
        "payload": {"pool_id": "default", "stake_id": "liq_x", "to": ADDRESS, "amount": 5},
    }


def test_pending_resubmission_returns_hash(monkeypatch):
    _client(monkeypatch, status_record={"state": "pending", "previously_rejected": True})

    assert wallet_staking._submit_liquidity_transaction(_ctx(), _wallet_data(), _tx()) == TX_HASH


def test_confirmed_or_unknown_record_returns_hash(monkeypatch):
    _client(monkeypatch, status_record={"status": "confirmed", "block_height": 36130})

    assert wallet_staking._submit_liquidity_transaction(_ctx(), _wallet_data(), _tx()) == TX_HASH


def test_rejected_record_fails_instead_of_echoing_corpse(monkeypatch):
    """The reported bug: CLI printed tx=<rejected hash> as 'Submitted'."""
    _client(
        monkeypatch,
        status_record={"status": "rejected", "rejected_reason": "Invalid nonce: expected 187, got 188"},
    )

    with pytest.raises(click.ClickException, match="previously rejected"):
        wallet_staking._submit_liquidity_transaction(_ctx(), _wallet_data(), _tx())


def test_status_probe_failure_is_advisory(monkeypatch):
    """Admission already succeeded — a failed status read must not fail the submit."""
    _client(monkeypatch, status_exc=RuntimeError("rpc down"))

    assert wallet_staking._submit_liquidity_transaction(_ctx(), _wallet_data(), _tx()) == TX_HASH
