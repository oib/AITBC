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

from aitbc_cli.utils.nonce import NonceClassificationError

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


# --- #2745: --retry-rejected requires the classified nonce view --------------


def _attempt_tx() -> dict:
    tx = _tx()
    tx["payload"]["attempt_id"] = "a" * 32
    return tx


def _nonce_client(monkeypatch, mempool_data, mempool_exc=None, status_record=None):
    """Like ``_client`` but the mempool probe returns ``mempool_data`` and
    every requested path is recorded for query assertions."""
    client = Mock()
    client.post.return_value = {"transaction_hash": TX_HASH}
    paths: list[str] = []

    def _get(path: str):
        paths.append(path)
        if "/rpc/mempool" in path:
            if mempool_exc is not None:
                raise mempool_exc
            return mempool_data
        if "/rpc/transaction/" in path:
            return status_record or {}
        if "/rpc/account/" in path:
            return {"nonce": 0}
        return {}

    client.get.side_effect = _get
    monkeypatch.setattr(wallet_staking, "AITBCHTTPClient", lambda *a, **k: client)
    return client, paths


def test_attempt_id_retry_fails_on_legacy_unmarked_mempool(monkeypatch):
    """attempt_id marks an explicit retry: a node without the classified view
    must stop the submit before signing or POSTing anything."""
    client, paths = _nonce_client(monkeypatch, {})
    sign = Mock()
    monkeypatch.setattr(wallet_staking, "_sign_transaction", sign)

    with pytest.raises(NonceClassificationError, match="rejection-aware"):
        wallet_staking._submit_liquidity_transaction(_ctx(), _wallet_data(), _attempt_tx())

    sign.assert_not_called()
    client.post.assert_not_called()
    assert any("nonce_view=true" in p for p in paths)


def test_attempt_id_retry_fails_on_explicit_incomplete_view(monkeypatch):
    """``nonce_view_complete: false`` is a known cannot-classify — fail
    closed even though the flag asked for the view."""
    client, _paths = _nonce_client(
        monkeypatch,
        {"success": False, "nonce_view_complete": False, "transactions": [], "count": 0},
    )
    sign = Mock()
    monkeypatch.setattr(wallet_staking, "_sign_transaction", sign)

    with pytest.raises(NonceClassificationError, match="Could not classify"):
        wallet_staking._submit_liquidity_transaction(_ctx(), _wallet_data(), _attempt_tx())

    sign.assert_not_called()
    client.post.assert_not_called()


def test_attempt_id_retry_fails_on_transport_error(monkeypatch):
    """A probe that cannot be read must not fall back to the legacy count —
    the retry would sign a nonce the node never cleared."""
    from aitbc.exceptions import NetworkError

    client, _paths = _nonce_client(monkeypatch, None, mempool_exc=NetworkError("down"))
    sign = Mock()
    monkeypatch.setattr(wallet_staking, "_sign_transaction", sign)

    with pytest.raises(NonceClassificationError, match="Could not read"):
        wallet_staking._submit_liquidity_transaction(_ctx(), _wallet_data(), _attempt_tx())

    sign.assert_not_called()
    client.post.assert_not_called()


def test_attempt_id_retry_proceeds_on_classified_view(monkeypatch):
    """Happy path: classified view frees the slot, the real signer runs
    (unmocked), exactly one POST carries the attempt-tagged envelope, and
    the occupied classified nonce is skipped."""
    client, paths = _nonce_client(
        monkeypatch,
        {
            "success": True,
            "nonce_view_complete": True,
            "transactions": [{"from": ADDRESS, "nonce": 0, "state": "pending"}],
            "count": 1,
        },
    )

    assert wallet_staking._submit_liquidity_transaction(_ctx(), _wallet_data(), _attempt_tx()) == TX_HASH

    assert client.post.call_count == 1
    posted = client.post.call_args.kwargs["json"]
    assert posted["nonce"] == 1  # sealed 0, classified view holds slot 0
    assert posted["payload"]["attempt_id"] == "a" * 32
    assert posted["signature"]
    assert any("nonce_view=true" in p for p in paths)


def test_plain_liquidity_tx_keeps_legacy_nonce_semantics(monkeypatch):
    """Without attempt_id the probe stays non-strict: ordinary clients now
    request ``nonce_view=true`` on every send, and a node predating the
    parameter ignores it — its unmarked answer still counts every occupant,
    so the submit proceeds exactly as before."""
    client, paths = _nonce_client(monkeypatch, {"transactions": [{"from": ADDRESS, "nonce": 0}]})

    assert wallet_staking._submit_liquidity_transaction(_ctx(), _wallet_data(), _tx()) == TX_HASH

    assert client.post.call_count == 1
    posted = client.post.call_args.kwargs["json"]
    assert posted["nonce"] == 1
    assert "attempt_id" not in posted["payload"]
    assert any("nonce_view=true" in p for p in paths)
