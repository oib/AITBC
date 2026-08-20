"""Safe local integration tests for marketplace and escrow commands."""

import os
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

os.environ["AITBC_SKIP_ENV_FILES"] = "1"

from aitbc_cli.core.main import cli


@pytest.fixture
def mock_marketplace_config(monkeypatch):
    """Patch get_config / load_multichain_config for local endpoints."""
    config = SimpleNamespace(
        marketplace_service_url="http://127.0.0.1:8102",
        blockchain_rpc_url="http://127.0.0.1:8202",
        exchange_service_url="http://127.0.0.1:8106",
        hub_discovery_url="",
    )

    def _get_config():
        return config

    monkeypatch.setattr("aitbc_cli.commands.marketplace_cmd.get_config", _get_config)
    monkeypatch.setattr("aitbc_cli.commands.market.escrow.get_config", _get_config)
    monkeypatch.setattr(
        "aitbc_cli.commands.marketplace_cmd.load_multichain_config",
        lambda: SimpleNamespace(blockchain_rpc_url="http://127.0.0.1:8202"),
    )
    return config


@pytest.fixture
def mock_http_client(monkeypatch):
    """Replace AITBCHTTPClient with a fake that records calls."""
    calls = {"get": [], "post": []}

    class FakeClient:
        def __init__(self, base_url=None, timeout=10, headers=None):
            self.base_url = base_url or "http://127.0.0.1:8202"

        def get(self, path, **kwargs):
            calls["get"].append((self.base_url, path, kwargs))
            return {"supported_chains": ["ait-hub.aitbc.bubuit.net"]}

        def post(self, path, **kwargs):
            calls["post"].append((self.base_url, path, kwargs))
            if path == "/rpc/escrow/create":
                return {"contract_id": "escrow-abc"}
            if path == "/v1/transactions":
                return {"transaction_id": "tx-123"}
            return {}

    # Patch the AITBCHTTPClient class everywhere it is imported in market modules.
    monkeypatch.setattr("aitbc_cli.commands.marketplace_cmd.AITBCHTTPClient", FakeClient)
    monkeypatch.setattr("aitbc_cli.commands.market.escrow.AITBCHTTPClient", FakeClient)
    # ``marketplace_cmd.list`` re-imports AITBCHTTPClient inside the command body.
    monkeypatch.setattr("aitbc_cli.utils.http_client.AITBCHTTPClient", FakeClient)
    return calls


def test_marketplace_create_posts_to_local_service(mock_marketplace_config, mock_http_client):
    """The marketplace create command posts a chain listing to the local marketplace service."""
    calls = mock_http_client
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "marketplace",
            "create",
            "chain-1",
            "Local Chain",
            "research",
            "A local chain for testing",
            "seller-1",
            "10.0",
        ],
    )
    assert result.exit_code == 0, result.output
    assert any(
        path == "/v1/transactions" for _, path, _ in calls["post"]
    ), f"Calls: {calls['post']}"


def test_market_escrow_create_posts_to_local_blockchain(mock_marketplace_config, mock_http_client):
    """The ``market escrow create`` command posts to the local blockchain RPC."""
    calls = mock_http_client
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "market",
            "escrow",
            "create",
            "job-1",
            "ait1" + "0" * 40,
            "ait1" + "1" * 40,
            "2.5",
        ],
    )
    assert result.exit_code == 0, result.output
    assert any(path == "/rpc/escrow/create" for _, path, _ in calls["post"])
    _, path, kwargs = next((b, p, k) for b, p, k in calls["post"] if p == "/rpc/escrow/create")
    payload = kwargs["json"]
    assert payload["job_id"] == "job-1"
    assert payload["amount"] == "2.5"
