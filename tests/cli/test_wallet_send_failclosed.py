"""Fail-closed tests for `aitbc wallet send` (Task 73).

A failed chain-id or nonce lookup must abort the command — never fall back
to a default chain id or nonce 0 for a signed send — and the default RPC
endpoint is the configured node RPC, never silently rewritten to the hub's
public URL (that name does not even resolve on the hub itself).
"""

import json
from unittest.mock import Mock, patch

import pytest
from aitbc_cli.commands.wallet import wallet
from click.testing import CliRunner

from aitbc_cli.utils.http_client import NetworkError

WALLET_ADDRESS = "0xDb5247d03cA2e40f3995A583b2C097Ab703efD4d"
TO_ADDRESS = "0xABCDabcdABcDabcDaBCDAbcdABcdAbCdABcDABCd"
LOCAL_RPC = "http://127.0.0.1:8202"
HUB_RPC = "https://hub.example.net/rpc"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_wallet(tmp_path):
    path = tmp_path / "sender.json"
    path.write_text(
        json.dumps(
            {
                "wallet_id": "sender",
                "address": WALLET_ADDRESS,
                "private_key": "a" * 64,
                "created_at": "2024-01-01T00:00:00",
            }
        )
    )
    return str(path)


@pytest.fixture
def node_http():
    """Fake blockchain node client plus a controlled CLI config.

    ``send`` and the chain-id helper each build their own client, and the
    wallet group callback + ``send`` each call ``get_config``, so the same
    doubles are patched into every namespace that looks those names up.
    """
    client = Mock()
    client.post = Mock(return_value={"transaction_hash": "0xdeadbeef"})

    def default_get(path, **kwargs):
        if "/rpc/proposer" in path or "/health" in path:
            return {"chain_id": "ait-node-chain", "supported_chains": ["ait-node-chain"]}
        if "/rpc/account/" in path or "/rpc/accounts/" in path:
            return {"balance": 0, "nonce": 7}
        return {}

    client.get = Mock(side_effect=default_get)

    config = Mock()
    config.blockchain_rpc_url = LOCAL_RPC
    config.hub_blockchain_rpc_url = HUB_RPC
    config.hub_discovery_url = "hub.example.net"

    with (
        patch("aitbc_cli.commands.wallet.basic.AITBCHTTPClient", return_value=client) as cls_basic,
        patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=client) as cls_chain,
        patch("aitbc_cli.commands.wallet.basic.get_wallet_client") as gw,
        patch("aitbc_cli.commands.wallet.basic.get_config", return_value=config),
        patch("aitbc_cli.commands.wallet.get_config", return_value=config),
    ):
        gw.return_value.get.return_value = {"items": []}
        yield {"client": client, "cls_basic": cls_basic, "cls_chain": cls_chain, "config": config}


def _send_args(temp_wallet, extra=None):
    args = [
        "--wallet-path",
        temp_wallet,
        "send",
        "--to-address",
        TO_ADDRESS,
        "--amount",
        "1.0",
    ]
    return args + (extra or [])


def _constructed_base_urls(*mock_classes):
    urls = []
    for cls in mock_classes:
        for call in cls.call_args_list:
            urls.append(call.kwargs.get("base_url") or (call.args[0] if call.args else None))
    return urls


class TestWalletSendFailClosed:
    def test_chain_id_lookup_failure_aborts_before_signing(self, runner, temp_wallet, node_http, monkeypatch):
        """RPC failure on the chain-id lookup exits non-zero and nothing is submitted."""
        monkeypatch.delenv("CHAIN_ID", raising=False)
        node_http["client"].get = Mock(side_effect=NetworkError("connection refused"))

        result = runner.invoke(wallet, _send_args(temp_wallet), obj={"output_format": "json"})

        assert result.exit_code != 0
        assert "Chain ID lookup" in result.output
        node_http["client"].post.assert_not_called()

    def test_nonce_lookup_failure_aborts_before_signing(self, runner, temp_wallet, node_http, monkeypatch):
        """RPC failure on the nonce lookup exits non-zero and nothing is submitted."""
        monkeypatch.delenv("CHAIN_ID", raising=False)

        def get(path, **kwargs):
            if "/rpc/proposer" in path or "/health" in path:
                return {"chain_id": "ait-node-chain"}
            raise NetworkError("connection refused")

        node_http["client"].get = Mock(side_effect=get)

        result = runner.invoke(wallet, _send_args(temp_wallet), obj={"output_format": "json"})

        assert result.exit_code != 0
        assert "Nonce lookup" in result.output
        node_http["client"].post.assert_not_called()

    def test_happy_path_uses_node_chain_id_and_nonce(self, runner, temp_wallet, node_http, monkeypatch):
        """Happy path signs with the chain id and nonce the mocked node advertised."""
        monkeypatch.delenv("CHAIN_ID", raising=False)

        result = runner.invoke(wallet, _send_args(temp_wallet), obj={"output_format": "json"})

        assert result.exit_code == 0, result.output
        node_http["client"].post.assert_called_once()
        submitted = node_http["client"].post.call_args.kwargs["json"]
        assert submitted["chain_id"] == "ait-node-chain"
        assert submitted["nonce"] == 7
        assert submitted["from"] == WALLET_ADDRESS
        assert submitted["signature"]

    def test_rpc_url_flag_is_honored(self, runner, temp_wallet, node_http, monkeypatch):
        """--rpc-url is used for the lookups and the submit; the hub URL never appears."""
        monkeypatch.delenv("CHAIN_ID", raising=False)

        result = runner.invoke(
            wallet,
            _send_args(temp_wallet, ["--rpc-url", "http://custom-node:9999"]),
            obj={"output_format": "json"},
        )

        assert result.exit_code == 0, result.output
        urls = _constructed_base_urls(node_http["cls_basic"], node_http["cls_chain"])
        assert "http://custom-node:9999" in urls
        assert HUB_RPC not in urls and "https://hub.example.net" not in urls

    def test_local_default_is_not_rewritten_to_hub(self, runner, temp_wallet, node_http, monkeypatch):
        """A local configured RPC is used as-is — never silently swapped for the hub URL."""
        monkeypatch.delenv("CHAIN_ID", raising=False)

        result = runner.invoke(wallet, _send_args(temp_wallet), obj={"output_format": "json"})

        assert result.exit_code == 0, result.output
        urls = _constructed_base_urls(node_http["cls_basic"], node_http["cls_chain"])
        assert urls
        assert set(urls) == {LOCAL_RPC}, urls


class TestMarketChainIdFailClosed:
    """The market module's own chain-id resolver must not fabricate ``ait-<host>``."""

    def _no_credentials(self):
        return patch(
            "aitbc_cli.commands.market.load_island_credentials",
            side_effect=FileNotFoundError("no creds file"),
        )

    def test_credentials_win(self):
        from aitbc_cli.commands.market import get_chain_id

        with patch(
            "aitbc_cli.commands.market.load_island_credentials",
            return_value={"island_chain_id": "ait-credchain"},
        ):
            assert get_chain_id() == "ait-credchain"

    def test_env_beats_probe_when_credentials_absent(self, monkeypatch):
        from aitbc_cli.commands.market import get_chain_id

        monkeypatch.setenv("CHAIN_ID", "ait-envchain")
        with self._no_credentials():
            assert get_chain_id() == "ait-envchain"

    def test_probe_used_when_credentials_and_env_absent(self, monkeypatch):
        from aitbc_cli.commands.market import get_chain_id

        monkeypatch.delenv("CHAIN_ID", raising=False)
        client = Mock()
        client.get = Mock(return_value={"chain_id": "ait-probed"})
        with self._no_credentials(), patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=client):
            assert get_chain_id() == "ait-probed"

    def test_aborts_instead_of_fabricating(self, monkeypatch):
        """No credentials, no CHAIN_ID, dead RPC → abort, never ``ait-<hostname>``."""
        import click
        from aitbc_cli.commands.market import get_chain_id

        monkeypatch.delenv("CHAIN_ID", raising=False)
        client = Mock()
        client.get = Mock(side_effect=NetworkError("connection refused"))
        with self._no_credentials(), patch("aitbc_cli.utils.chain_id.AITBCHTTPClient", return_value=client):
            with pytest.raises(click.Abort):
                get_chain_id()
