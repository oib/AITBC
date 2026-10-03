"""Wallet signing paths must abort loudly when the chain-id or nonce lookup fails.

Regression tests for the 2 Oct hub incident: a silent ``ait-localnet``/nonce-0
fallback signed a transaction for a chain nobody serves. The lookup must abort
the command naming the RPC URL and the underlying error; an explicit
``--chain-id`` or ``CHAIN_ID`` still wins over the lookup.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

import aitbc_cli.utils.chain_id as chain_id_mod
from aitbc_cli.commands.wallet import wallet
from aitbc_cli.commands.wallet import staking as staking_mod


def _write_wallet(tmp_path: Path) -> Path:
    """A plaintext file wallet: real-looking key material, no encryption."""
    wallet_file = tmp_path / "testwallet.json"
    wallet_file.write_text(
        json.dumps(
            {
                "address": "0x08aB1234567890abcdef1234567890abcdef1234",
                "private_key": "0x" + "11" * 32,
                "encrypted": False,
            }
        )
    )
    return wallet_file


def _fake_http_client(get_data=None, get_exc=None, post_data=None):
    """AITBCHTTPClient stand-in recording construction URLs and POST bodies."""

    class _FakeClient:
        instances: list["_FakeClient"] = []

        def __init__(self, base_url: str = "", **kwargs):
            self.base_url = base_url
            self.posts: list[tuple[str, dict]] = []
            _FakeClient.instances.append(self)

        def get(self, endpoint: str, **kwargs):
            if get_exc is not None:
                raise get_exc
            return get_data or {}

        def post(self, endpoint: str, json=None, **kwargs):
            self.posts.append((endpoint, json))
            return post_data or {"transaction_hash": "0xdeadbeef"}

    _FakeClient.instances = []
    return _FakeClient


def _failing_chain_lookup(rpc_url, override=None, timeout=5, *, strict=False):
    """Group-init resolution yields ""; a strict probe raises like a dead RPC."""
    if override:
        return override
    if strict:
        raise chain_id_mod.ChainIdLookupError(f"{rpc_url}: connection refused")
    return ""


def _serving_chain_lookup(chain_id):
    def _fake(rpc_url, override=None, timeout=5, *, strict=False):
        return override or chain_id

    return _fake


@pytest.fixture
def runner():
    return CliRunner()


SEND_ARGS = ["send", "--to-address", "0x1234567890abcdef1234567890abcdef12345678", "--amount", "1"]


def test_send_aborts_when_chain_id_lookup_fails(runner, tmp_path, monkeypatch):
    """A dead RPC must abort send before signing — never a silent ait-localnet."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={"nonce": 5})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), *SEND_ARGS, "--rpc-url", "http://127.0.0.1:1"],
            obj={},
        )
    assert result.exit_code != 0
    assert "127.0.0.1:1" in result.output
    assert "--rpc-url" in result.output
    assert all(not post for post in [c.posts for c in fake_client.instances])


def test_send_aborts_when_nonce_lookup_fails(runner, tmp_path, monkeypatch):
    """A failed account lookup must abort — never silently sign nonce 0."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_exc=RuntimeError("connection refused"))
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-test")),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), *SEND_ARGS, "--rpc-url", "http://127.0.0.1:2"],
            obj={},
        )
    assert result.exit_code != 0
    assert "127.0.0.1:2" in result.output
    assert "--rpc-url" in result.output
    assert all(not c.posts for c in fake_client.instances)


def test_send_uses_looked_up_chain_and_nonce(runner, tmp_path, monkeypatch):
    """Successful lookups behave exactly as before: sign + submit."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={"nonce": 7})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-testnet")),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), *SEND_ARGS, "--rpc-url", "http://10.0.0.9:8202"],
            obj={},
        )
    assert result.exit_code == 0, result.output
    submitted = [body for c in fake_client.instances for ep, body in c.posts if ep == "/rpc/transaction"]
    assert submitted, result.output
    tx = submitted[-1]
    assert tx["chain_id"] == "ait-testnet"
    assert tx["nonce"] == 7
    assert tx["signature"]


def test_send_explicit_chain_id_flag_wins_over_failed_lookup(runner, tmp_path, monkeypatch):
    """wallet --chain-id beats a failed probe: signs for the explicit chain."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={"nonce": 3})
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), "--chain-id", "explicit-chain", *SEND_ARGS],
            obj={},
        )
    assert result.exit_code == 0, result.output
    submitted = [body for c in fake_client.instances for ep, body in c.posts if ep == "/rpc/transaction"]
    assert submitted and submitted[-1]["chain_id"] == "explicit-chain"


def test_send_chain_id_env_wins_over_failed_lookup(runner, tmp_path, monkeypatch):
    """CHAIN_ID env supplied by the user beats a failed probe."""
    wallet_path = _write_wallet(tmp_path)
    fake_client = _fake_http_client(get_data={"nonce": 4})
    monkeypatch.setenv("CHAIN_ID", "env-chain")
    with (
        patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup),
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", fake_client),
    ):
        result = runner.invoke(
            wallet,
            ["--wallet-path", str(wallet_path), *SEND_ARGS],
            obj={},
        )
    assert result.exit_code == 0, result.output
    submitted = [body for c in fake_client.instances for ep, body in c.posts if ep == "/rpc/transaction"]
    assert submitted and submitted[-1]["chain_id"] == "env-chain"


def _ctx(obj: dict | None = None) -> click.Context:
    ctx = click.Context(click.Command("wallet-test"))
    ctx.obj = obj or {}
    return ctx


def test_staking_get_chain_id_aborts_when_lookup_fails(monkeypatch):
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup):
        with pytest.raises(click.Abort):
            staking_mod._get_chain_id(_ctx(), "http://127.0.0.1:1")


def test_staking_get_chain_id_reuses_group_resolution(monkeypatch):
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with patch.object(chain_id_mod, "get_chain_id", side_effect=_failing_chain_lookup):
        assert staking_mod._get_chain_id(_ctx({"chain_id": "ait-detected"}), "http://x") == "ait-detected"


def test_staking_get_chain_id_explicit_wins(monkeypatch):
    monkeypatch.delenv("CHAIN_ID", raising=False)
    ctx = _ctx({"chain_id": "ait-detected", "chain_id_explicit": "ait-flag"})
    assert staking_mod._get_chain_id(ctx, "http://x") == "ait-flag"


def test_staking_get_chain_id_env_wins(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "ait-env")
    assert staking_mod._get_chain_id(_ctx(), "http://x") == "ait-env"


def test_staking_get_chain_id_strict_probe_success(monkeypatch):
    monkeypatch.delenv("CHAIN_ID", raising=False)
    with patch.object(chain_id_mod, "get_chain_id", side_effect=_serving_chain_lookup("ait-probed")):
        assert staking_mod._get_chain_id(_ctx(), "http://node:8202") == "ait-probed"


def test_get_account_nonce_aborts_on_lookup_failure():
    client = MagicMock()
    client.base_url = "http://127.0.0.1:1"
    client.get.side_effect = RuntimeError("connection refused")
    with pytest.raises(click.Abort):
        staking_mod._get_account_nonce(client, "0xabc", "ait-test")


def test_get_account_nonce_returns_nonce_on_success():
    client = MagicMock()
    client.base_url = "http://node:8202"
    client.get.return_value = {"nonce": 9}
    assert staking_mod._get_account_nonce(client, "0xabc", "ait-test") == 9
