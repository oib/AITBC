"""Safe local integration tests for the ``aitbc ai`` command group."""

import os
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

os.environ["AITBC_SKIP_ENV_FILES"] = "1"

from aitbc_cli.core.main import cli


@pytest.fixture
def mock_config(monkeypatch):
    """Patch get_config with safe local defaults."""
    config = SimpleNamespace(
        coordinator_api_url="http://127.0.0.1:8203",
        blockchain_rpc_url="http://127.0.0.1:8202",
        chain_id="ait-hub.aitbc.bubuit.net",
    )

    def _get_config():
        return config

    monkeypatch.setattr("aitbc_cli.commands.ai.get_config", _get_config)
    return config


@pytest.fixture
def mock_http_client(monkeypatch):
    """Replace AITBCHTTPClient with a fake that records calls."""
    calls = {"get": [], "post": []}

    class FakeClient:
        def __init__(self, base_url=None, timeout=10, headers=None, **kwargs):
            self.base_url = base_url or "http://127.0.0.1:8203"
            self.headers = headers

        def get(self, path, **kwargs):
            calls["get"].append((self.base_url, path, kwargs))
            return {"jobs": []}

        def post(self, path, **kwargs):
            calls["post"].append((self.base_url, path, kwargs))
            return {"job_id": "job-123"}

    monkeypatch.setattr("aitbc_cli.commands.ai.AITBCHTTPClient", FakeClient)
    return calls


def test_ai_submit_reaches_local_coordinator(mock_config, mock_http_client):
    """Submitting an AI job posts to the local coordinator API."""
    calls = mock_http_client
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ai",
            "submit",
            "--prompt",
            "Hello local model",
            "--model",
            "llama2",
            "--payment",
            "0.5",
            "--buyer-address",
            "0x11a01cb7F3C01AE8E8a992FE72fbDF3B530ccdD7",
            "--provider-address",
            "0xEd34ECBd91d29f7E13213ba321F5E7Fc8830a450",
            "--coordinator-url",
            "http://127.0.0.1:8203",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(calls["post"]) == 1
    base_url, path, kwargs = calls["post"][0]
    assert base_url == "http://127.0.0.1:8203"
    assert path == "/v1/jobs"
    payload = kwargs["json"]
    assert payload["payload"]["prompt"] == "Hello local model"
    assert payload["payload"]["model"] == "llama2"
    assert payload["payment_amount"] == "0.5"
    assert payload["payment_currency"] == "AITBC"


def test_ai_jobs_uses_local_coordinator(mock_config, mock_http_client):
    """Listing jobs queries the local coordinator API."""
    calls = mock_http_client
    runner = CliRunner()
    result = runner.invoke(cli, ["ai", "jobs", "--limit", "5", "--coordinator-url", "http://127.0.0.1:8203"])
    assert result.exit_code == 0, result.output
    assert len(calls["get"]) == 1
    base_url, path, kwargs = calls["get"][0]
    assert base_url == "http://127.0.0.1:8203"
    assert path == "/v1/jobs"
    assert kwargs["params"]["limit"] == 5
