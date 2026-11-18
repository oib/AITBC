"""CLI dispute write auth — X-Wallet-Address header (#2243).

The chain RPC dispute write routes authenticate solely via the
``X-Wallet-Address`` header, honoured only when the node sets
``TRUST_X_WALLET_ADDRESS=true`` and sees a loopback client. The CLI must
expose a ``--wallet`` path that resolves a keystore name to its address and
attach the header; a 401 must produce the trust/loopback hint, not a bare
RPC error.
"""

import json

import pytest
import requests
from click.testing import CliRunner

import aitbc_cli.commands.dispute as dispute_mod
from aitbc_cli.commands.dispute import dispute
from aitbc_cli.utils.http_client import NetworkError


@pytest.fixture
def runner():
    return CliRunner()


def _network_error(status_code: int) -> NetworkError:
    response = requests.models.Response()
    response.status_code = status_code
    response.url = "http://node.test/rpc/disputes/file"
    http_error = requests.HTTPError(f"{status_code} Client Error", response=response)
    err = NetworkError(f"POST request failed: {http_error}")
    err.__cause__ = http_error
    return err


class _RecordingClient:
    """Captures constructor kwargs and returns a canned success."""

    instances: list["_RecordingClient"] = []

    def __init__(self, base_url, timeout=10, **kwargs):
        self.base_url = base_url
        self.kwargs = kwargs
        self.posts: list[tuple[str, dict]] = []
        _RecordingClient.instances.append(self)

    def post(self, path, json=None, **kwargs):
        self.posts.append((path, json or {}))
        return {"success": True}

    def get(self, path, params=None):
        return {"success": True}

    def get_json(self, path, params=None, headers=None):
        return []

    def close(self):
        pass


@pytest.fixture
def recording_client(monkeypatch):
    _RecordingClient.instances = []
    monkeypatch.setattr(dispute_mod, "AITBCHTTPClient", _RecordingClient)
    return _RecordingClient


@pytest.fixture
def wallet_file(tmp_path, monkeypatch):
    """Point find_wallet_file at a fake keystore holding a known address."""
    address = "0xAbCdEf00000000000000000000000000000001"
    path = tmp_path / "mywallet.json"
    path.write_text(json.dumps({"address": address, "crypto": {}}))
    monkeypatch.setattr(dispute_mod, "find_wallet_file", lambda name: path if name == "mywallet" else None)
    return address


def _invoke_write(runner, args, **kwargs):
    return runner.invoke(dispute, obj={"output_format": "table"}, args=args, **kwargs)


class TestWalletHeader:
    def test_file_sends_x_wallet_address(self, runner, recording_client, wallet_file):
        result = _invoke_write(
            runner,
            [
                "file",
                "--agreement-id",
                "7",
                "--respondent",
                "0xresp",
                "--dispute-type",
                "non_delivery",
                "--reason",
                "no result",
                "--evidence-hash",
                "0xhash",
                "--wallet",
                "mywallet",
            ],
        )
        assert result.exit_code == 0, result.output
        client = recording_client.instances[-1]
        assert client.kwargs["headers"] == {"X-Wallet-Address": wallet_file}

    def test_file_without_wallet_sends_no_header(self, runner, recording_client, monkeypatch):
        monkeypatch.delenv("AITBC_DEFAULT_WALLET", raising=False)
        monkeypatch.setattr(dispute_mod, "get_config", lambda: _ConfigStub())
        result = _invoke_write(
            runner,
            [
                "file",
                "--agreement-id",
                "7",
                "--respondent",
                "0xresp",
                "--dispute-type",
                "non_delivery",
                "--reason",
                "no result",
                "--evidence-hash",
                "0xhash",
            ],
        )
        assert result.exit_code == 0, result.output
        client = recording_client.instances[-1]
        assert "headers" not in client.kwargs

    def test_default_wallet_env_used(self, runner, recording_client, wallet_file, monkeypatch):
        monkeypatch.setenv("AITBC_DEFAULT_WALLET", "mywallet")
        monkeypatch.setattr(dispute_mod, "get_config", lambda: _ConfigStub())
        result = _invoke_write(
            runner,
            [
                "vote",
                "--dispute-id",
                "3",
                "--vote",
                "plaintiff",
                "--reasoning",
                "clear",
            ],
        )
        assert result.exit_code == 0, result.output
        client = recording_client.instances[-1]
        assert client.kwargs["headers"] == {"X-Wallet-Address": wallet_file}

    def test_unknown_wallet_aborts(self, runner, monkeypatch):
        monkeypatch.setattr(dispute_mod, "find_wallet_file", lambda name: None)
        result = _invoke_write(
            runner,
            [
                "file",
                "--agreement-id",
                "7",
                "--respondent",
                "0xresp",
                "--dispute-type",
                "non_delivery",
                "--reason",
                "no result",
                "--evidence-hash",
                "0xhash",
                "--wallet",
                "ghost",
            ],
        )
        assert result.exit_code != 0
        assert "ghost" in result.output


class _ConfigStub:
    blockchain_rpc_url = "http://node.test:8202"
    blockchain_rpc_api_key = ""
    timeout = 5
    wallet_address = None


class TestUnauthorizedHint:
    def test_401_shows_trust_and_loopback_hint(self, runner, monkeypatch):
        class C:
            def __init__(self, base_url, timeout=10, **kwargs):
                self.base_url = base_url

            def post(self, path, json=None, **kwargs):
                raise _network_error(401)

        monkeypatch.setattr(dispute_mod, "AITBCHTTPClient", C)
        result = _invoke_write(
            runner,
            ["vote", "--dispute-id", "3", "--vote", "plaintiff", "--reasoning", "x"],
        )
        assert result.exit_code != 0
        assert "TRUST_X_WALLET_ADDRESS" in result.output
        assert "loopback" in result.output.lower()

    def test_500_keeps_plain_rpc_error(self, runner, monkeypatch):
        class C:
            def __init__(self, base_url, timeout=10, **kwargs):
                self.base_url = base_url

            def post(self, path, json=None, **kwargs):
                raise _network_error(500)

        monkeypatch.setattr(dispute_mod, "AITBCHTTPClient", C)
        result = _invoke_write(
            runner,
            ["vote", "--dispute-id", "3", "--vote", "plaintiff", "--reasoning", "x"],
        )
        assert result.exit_code != 0
        assert "Blockchain RPC error" in result.output
        assert "TRUST_X_WALLET_ADDRESS" not in result.output
