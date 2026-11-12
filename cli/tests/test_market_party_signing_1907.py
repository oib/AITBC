"""Pins for #1907: market CLI party-signature fields and operator-key resolution.

After the #1893 operator-tier split, the market service's object-scoped
mutation routes (jobs release/refund/dispute/cancel, offer book/cancel)
return 403 for unsigned user-key requests. These tests pin that the CLI
now (a) resolves MARKET_OPERATOR_API_KEY for operators and (b) attaches a
verifiable job-party signature to the release/refund sync payloads.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner
from eth_account import Account

from aitbc.crypto.signature_recovery import canonical_address
from aitbc.market.job_request_signature import verify_jobs_request_signature
from aitbc_cli.commands.market._signing import signed_job_request_fields
from aitbc_cli.config import CLIConfig, _resolve_market_api_key


@pytest.fixture
def market_wallet():
    """A real secp256k1 keypair so signatures verify end-to-end."""
    account = Account.create()
    return account.address, "0x" + account.key.hex(), "test-wallet"


def _cfg(api_key: str | None = None) -> CLIConfig:
    return CLIConfig(api_key=api_key, market_service_url="http://market.example:8102", _env_file=[])


# --- operator-tier key resolution -------------------------------------------


def test_operator_env_key_wins_over_user_key(monkeypatch):
    monkeypatch.setenv("MARKET_OPERATOR_API_KEY", "operator-key")
    monkeypatch.setenv("MARKET_API_KEY", "user-key")
    assert _resolve_market_api_key(_cfg(api_key="generic")) == "operator-key"


def test_operator_env_file_key_used_when_no_env_or_config(monkeypatch, tmp_path):
    monkeypatch.delenv("MARKET_OPERATOR_API_KEY", raising=False)
    monkeypatch.delenv("MARKET_API_KEY", raising=False)
    env_file = tmp_path / "aitbc-market.env"
    env_file.write_text("API_KEY=user-key\nMARKET_OPERATOR_API_KEY=operator-key\n")
    with patch("aitbc_cli.config.Path") as mock_path:
        mock_path.return_value = env_file
        assert _resolve_market_api_key(_cfg()) == "operator-key"


def test_user_key_still_resolves_without_operator_key(monkeypatch, tmp_path):
    monkeypatch.delenv("MARKET_OPERATOR_API_KEY", raising=False)
    monkeypatch.delenv("MARKET_API_KEY", raising=False)
    env_file = tmp_path / "aitbc-market.env"
    env_file.write_text("API_KEY=user-key\n")
    with patch("aitbc_cli.config.Path") as mock_path:
        mock_path.return_value = env_file
        assert _resolve_market_api_key(_cfg()) == "user-key"


# --- signed_job_request_fields ----------------------------------------------


def test_signed_fields_verify_against_market_scheme(market_wallet, monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "ait-test")
    route = "/v1/market/jobs/job-1/refund"
    fields = signed_job_request_fields(None, route, wallet=market_wallet)
    assert set(fields) == {"signer_address", "chain_id", "issued_at", "signature"}
    error, signer = verify_jobs_request_signature(
        signer_address=fields["signer_address"],
        chain_id=fields["chain_id"],
        issued_at=fields["issued_at"],
        route=route,
        signature=fields["signature"],
        expected_chain_id="ait-test",
    )
    assert error is None
    assert signer is not None
    assert canonical_address(signer) == canonical_address(market_wallet[0])


def test_signed_fields_empty_without_private_key(market_wallet, monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "ait-test")
    address, _, name = market_wallet
    fields = signed_job_request_fields(None, "/v1/market/jobs/j/release", wallet=(address, None, name))
    assert fields == {}


def test_signed_fields_empty_when_signing_fails(market_wallet, monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "ait-test")
    with patch("aitbc_cli.commands.market.get_chain_id", side_effect=RuntimeError("no chain")):
        fields = signed_job_request_fields(None, "/v1/market/jobs/j/release", wallet=market_wallet)
    assert fields == {}


# --- gpu refund command payload ----------------------------------------------


def test_gpu_refund_posts_signed_payload(market_wallet, monkeypatch):
    """`market gpu refund` must attach job-party signature fields (#1907)."""
    from aitbc_cli.commands.market import gpu as gpu_module

    monkeypatch.setenv("CHAIN_ID", "ait-test")
    posted: dict = {}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def post(self, path, json=None):
            posted["path"] = path
            posted["json"] = json
            return {"status": "refunded"}

    monkeypatch.setattr(gpu_module, "load_wallet_for_payment", lambda *a, **k: market_wallet)
    monkeypatch.setattr(gpu_module, "AITBCHTTPClient", _FakeClient)
    monkeypatch.setattr(gpu_module, "get_config", lambda: _cfg())
    monkeypatch.setattr(gpu_module, "_resolve_market_api_key", lambda config: "user-key")

    runner = CliRunner()
    result = runner.invoke(
        gpu_module.refund,
        ["--job-id", "job-9", "--yes", "--json-output"],
        obj={},
    )
    assert result.exit_code == 0, result.output
    payload = posted["json"]
    assert posted["path"] == "/v1/market/jobs/job-9/refund"
    assert payload["signer_address"] == market_wallet[0]
    error, signer = verify_jobs_request_signature(
        signer_address=payload["signer_address"],
        chain_id=payload["chain_id"],
        issued_at=payload["issued_at"],
        route="/v1/market/jobs/job-9/refund",
        signature=payload["signature"],
        expected_chain_id="ait-test",
    )
    assert error is None
    assert signer is not None
    assert canonical_address(signer) == canonical_address(market_wallet[0])


# --- market run release sync payload -----------------------------------------


def test_release_sync_posts_signed_payload(market_wallet, monkeypatch):
    """`_release_market_payment` must sign the release route (#1907)."""
    import click

    from aitbc_cli.commands.market import host as host_module

    monkeypatch.setenv("CHAIN_ID", "ait-test")
    posted: dict = {}

    class _FakeClient:
        def post(self, path, json=None):
            posted["path"] = path
            posted["json"] = json
            return {"status": "released"}

    monkeypatch.setattr(
        host_module,
        "_post_escrow_release",
        lambda ctx, config, job_id, timeout=20: ({"tx_hash": "0xabc", "released_amount": 5}, []),
    )
    monkeypatch.setattr(host_module, "_market_client", lambda: _FakeClient())
    monkeypatch.setattr(host_module, "get_config", lambda: _cfg())
    monkeypatch.setattr(
        "aitbc_cli.commands.market.get_market_wallet",
        lambda ctx, require_private_key=False: market_wallet,
    )

    ctx = click.Context(click.Command("test"))
    ctx.obj = {}
    result = host_module._release_market_payment(ctx, "job-7")
    assert result == {"status": "released"}
    payload = posted["json"]
    assert posted["path"] == "/v1/market/jobs/job-7/release"
    error, signer = verify_jobs_request_signature(
        signer_address=payload["signer_address"],
        chain_id=payload["chain_id"],
        issued_at=payload["issued_at"],
        route="/v1/market/jobs/job-7/release",
        signature=payload["signature"],
        expected_chain_id="ait-test",
    )
    assert error is None
    assert signer is not None
    assert canonical_address(signer) == canonical_address(market_wallet[0])
