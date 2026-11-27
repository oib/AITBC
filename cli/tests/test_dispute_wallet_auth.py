"""CLI dispute write auth — wallet-signed requests (#3052).

The chain RPC dispute write routes authenticate with a wallet signature over
the request (``signature``/``issued_at``/``nonce`` in the body plus the
``X-Wallet-Address`` claimed-identity header). The CLI must resolve a keystore
with a private key, sign the canonical ``dispute_sign_data`` message, and
attach the proof; a 401/403 must produce the signing hint, not a bare RPC
error.
"""

import json

import pytest
import requests
from click.testing import CliRunner
from eth_keys import keys

import aitbc_cli.commands.dispute as dispute_mod
from aitbc_cli.commands.dispute import dispute
from aitbc_cli.utils.http_client import NetworkError

# A real secp256k1 key so load_wallet_for_payment's derived-address check and
# the signature itself are exercised end to end.
_PRIVATE_KEY = "11" * 32
_PRIVATE_KEY_OBJ = keys.PrivateKey(bytes.fromhex(_PRIVATE_KEY))
ADDRESS = _PRIVATE_KEY_OBJ.public_key.to_checksum_address()


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
        # /rpc/info is probed for the chain id the signature binds (#3073).
        return {"chain_id": "test-chain", "success": True}

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
def wallet_dir(tmp_path, monkeypatch):
    """AITBC_WALLET_DIR holding 'mywallet' with a usable private key."""
    (tmp_path / "mywallet.json").write_text(json.dumps({"address": ADDRESS, "private_key": _PRIVATE_KEY}))
    monkeypatch.setenv("AITBC_WALLET_DIR", str(tmp_path))
    monkeypatch.delenv("AITBC_DEFAULT_WALLET", raising=False)
    return tmp_path


def _invoke_write(runner, args, **kwargs):
    return runner.invoke(dispute, obj={"output_format": "table"}, args=args, **kwargs)


class TestSignedBody:
    def test_file_sends_header_and_signature(self, runner, recording_client, wallet_dir):
        result = _invoke_write(
            runner,
            [
                "file",
                "--agreement-id",
                "7",
                "--respondent",
                "0xresp",
                "--dispute-type",
                "Payment",
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
        assert client.kwargs["headers"] == {"X-Wallet-Address": ADDRESS}
        path, body = client.posts[-1]
        assert path == "/rpc/disputes/file"
        assert body["signature"]
        assert isinstance(body["issued_at"], int)
        assert body["nonce"]
        # The signature must verify over the exact posted payload.
        from aitbc.blockchain.dispute_auth import dispute_sign_data
        from aitbc.crypto.signature_recovery import verify_signature
        from eth_utils import keccak

        payload = {k: v for k, v in body.items() if k not in ("signature", "issued_at", "nonce")}
        sign_data = dispute_sign_data(
            action="rpc/disputes/file",
            address=ADDRESS,
            payload=payload,
            issued_at=body["issued_at"],
            nonce=body["nonce"],
            chain_id="test-chain",
        )
        msg = json.dumps(sign_data, sort_keys=True, separators=(",", ":")).encode()
        assert verify_signature(keccak(msg), body["signature"], ADDRESS)

    def test_default_wallet_env_used(self, runner, recording_client, wallet_dir, monkeypatch):
        monkeypatch.setenv("AITBC_DEFAULT_WALLET", "mywallet")
        result = _invoke_write(
            runner,
            ["vote", "--dispute-id", "3", "--vote", "plaintiff", "--reasoning", "clear"],
        )
        assert result.exit_code == 0, result.output
        client = recording_client.instances[-1]
        assert client.kwargs["headers"] == {"X-Wallet-Address": ADDRESS}
        _, body = client.posts[-1]
        assert body["signature"]

    def test_evidence_and_verify_are_signed(self, runner, recording_client, wallet_dir):
        for args, path in [
            (
                [
                    "evidence",
                    "add",
                    "--dispute-id",
                    "3",
                    "--evidence-hash",
                    "0xh",
                    "--evidence-type",
                    "receipt",
                    "--description",
                    "d",
                    "--wallet",
                    "mywallet",
                ],
                "/rpc/disputes/evidence",
            ),
            (
                ["evidence", "verify", "--dispute-id", "3", "--evidence-id", "1", "--wallet", "mywallet"],
                "/rpc/disputes/verify-evidence",
            ),
        ]:
            result = _invoke_write(runner, args)
            assert result.exit_code == 0, result.output
            posted_path, body = recording_client.instances[-1].posts[-1]
            assert posted_path == path
            assert body["signature"] and body["nonce"]

    def test_no_wallet_aborts_with_signing_hint(self, runner, recording_client, wallet_dir, monkeypatch):
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
                "Payment",
                "--reason",
                "r",
                "--evidence-hash",
                "0xh",
            ],
        )
        assert result.exit_code != 0
        assert "signing wallet" in result.output.lower() or "--wallet" in result.output
        assert recording_client.instances == []

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
                "Payment",
                "--reason",
                "r",
                "--evidence-hash",
                "0xh",
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
    def test_401_shows_signing_hint(self, runner, wallet_dir, monkeypatch):
        class C:
            def __init__(self, base_url, timeout=10, **kwargs):
                self.base_url = base_url

            def get(self, path, params=None):
                return {"chain_id": "test-chain"}

            def post(self, path, json=None, **kwargs):
                raise _network_error(401)

        monkeypatch.setattr(dispute_mod, "AITBCHTTPClient", C)
        result = _invoke_write(
            runner,
            ["vote", "--dispute-id", "3", "--vote", "plaintiff", "--reasoning", "x", "--wallet", "mywallet"],
        )
        assert result.exit_code != 0
        assert "signature" in result.output.lower()

    def test_403_shows_signing_hint(self, runner, recording_client, wallet_dir, monkeypatch):
        class C:
            def __init__(self, base_url, timeout=10, **kwargs):
                self.base_url = base_url

            def get(self, path, params=None):
                return {"chain_id": "test-chain"}

            def post(self, path, json=None, **kwargs):
                raise _network_error(403)

        monkeypatch.setattr(dispute_mod, "AITBCHTTPClient", C)
        result = _invoke_write(
            runner,
            ["vote", "--dispute-id", "3", "--vote", "plaintiff", "--reasoning", "x", "--wallet", "mywallet"],
        )
        assert result.exit_code != 0
        assert "signature" in result.output.lower()

    def test_500_keeps_plain_rpc_error(self, runner, recording_client, wallet_dir, monkeypatch):
        class C:
            def __init__(self, base_url, timeout=10, **kwargs):
                self.base_url = base_url

            def get(self, path, params=None):
                return {"chain_id": "test-chain"}

            def post(self, path, json=None, **kwargs):
                raise _network_error(500)

        monkeypatch.setattr(dispute_mod, "AITBCHTTPClient", C)
        result = _invoke_write(
            runner,
            ["vote", "--dispute-id", "3", "--vote", "plaintiff", "--reasoning", "x", "--wallet", "mywallet"],
        )
        assert result.exit_code != 0
        assert "Blockchain RPC error" in result.output
        assert "signature" not in result.output.lower()
