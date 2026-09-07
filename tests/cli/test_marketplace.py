"""Safe local integration tests for marketplace and escrow commands."""

import os
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

os.environ["AITBC_SKIP_ENV_FILES"] = "1"

from aitbc_cli.core.main import cli


@pytest.fixture
def mock_marketplace_config(monkeypatch):
    """Patch get_config for local endpoints and a known hub proposer."""
    config = SimpleNamespace(
        marketplace_service_url="http://127.0.0.1:8102",
        blockchain_rpc_url="http://127.0.0.1:8202",
        exchange_service_url="http://127.0.0.1:8106",
        hub_discovery_url="",
        hub_proposer_id="0x1111111111111111111111111111111111111111",
        blockchain_rpc_api_key=None,
    )
    monkeypatch.setattr("aitbc_cli.commands.market.escrow.get_config", lambda: config)
    return config


@pytest.fixture
def mock_http_client(monkeypatch):
    """Replace AITBCHTTPClient with a fake that records calls."""
    calls = {"get": [], "post": []}

    class FakeClient:
        def __init__(self, base_url=None, timeout=10, headers=None, **kwargs):
            self.base_url = base_url or "http://127.0.0.1:8202"

        def get(self, path, **kwargs):
            calls["get"].append((self.base_url, path, kwargs))
            if path == "/health" or path.endswith("/health"):
                return {
                    "supported_chains": ["ait-hub.aitbc.bubuit.net"],
                    "proposer_id": "0x1111111111111111111111111111111111111111",
                }
            if "/rpc/account/" in path:
                return {"balance": 1000000000, "nonce": 0}
            return {"supported_chains": ["ait-hub.aitbc.bubuit.net"]}

        def post(self, path, **kwargs):
            calls["post"].append((self.base_url, path, kwargs))
            if path == "/rpc/escrow/create":
                return {"contract_id": "escrow-abc"}
            if path == "/v1/transactions":
                return {"transaction_id": "tx-123"}
            if path == "/rpc/transaction":
                return {"transaction_hash": "0xabc123"}
            return {}

    # ``market escrow`` and the escrow helpers import the client into their own
    # namespaces, so patch every copy.
    monkeypatch.setattr("aitbc_cli.commands.market.escrow.AITBCHTTPClient", FakeClient)
    monkeypatch.setattr("aitbc_cli.utils.escrow.AITBCHTTPClient", FakeClient)
    monkeypatch.setattr("aitbc_cli.utils.http_client.AITBCHTTPClient", FakeClient)
    # ``_escrow_create`` re-imports this at call time, so patching the source
    # module covers it — the signing and nonce round-trips are skipped.
    monkeypatch.setattr(
        "aitbc_cli.utils.escrow.create_signed_escrow_lock",
        lambda *args, **kwargs: ({"type": "ESCROW_LOCK"}, "0x" + "ab" * 64),
    )
    return calls


def test_market_escrow_create_posts_to_local_blockchain(mock_marketplace_config, mock_http_client):
    """``market escrow create`` posts the signed lock to the local blockchain RPC."""
    calls = mock_http_client
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "market",
            "escrow",
            "create",
            "--job-id",
            "job-1",
            "--buyer",
            "0x11a01cb7F3C01AE8E8a992FE72fbDF3B530ccdD7",
            "--provider",
            "0xEd34ECBd91d29f7E13213ba321F5E7Fc8830a450",
            "--amount",
            "2.5",
        ],
    )
    assert result.exit_code == 0, result.output
    assert any(path == "/rpc/escrow/create" for _, path, _ in calls["post"])
    _, path, kwargs = next((b, p, k) for b, p, k in calls["post"] if p == "/rpc/escrow/create")
    payload = kwargs["json"]
    assert payload["job_id"] == "job-1"
    assert payload["amount"] == "2.5"
