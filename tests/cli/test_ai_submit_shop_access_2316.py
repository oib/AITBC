"""Shop-access credential pins for ``ai submit --type transcribe`` (#2316, #2321).

The miner's whisper call is gated by per-job tokens the market service
issues; the buyer-side CLI is the only party holding the user-tier key
that mints them. ``_attach_shop_access`` must embed the credential triple
in the coordinator job payload for *paid* transcribe submits — and must
not fire for job types that never reach a gated shop, nor for unpaid
submits whose jobs are still dispatchable (#2321).
"""

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from click.testing import CliRunner

os.environ["AITBC_SKIP_ENV_FILES"] = "1"

from aitbc_cli.core.main import cli


@pytest.fixture
def mock_config(monkeypatch):
    monkeypatch.setenv("CHAIN_ID", "ait-testchain.local")
    monkeypatch.setattr("aitbc_cli.commands.ai.get_buyer_nonce", lambda *a, **k: 0)
    config = SimpleNamespace(
        coordinator_api_url="http://127.0.0.1:8203",
        blockchain_rpc_url="http://127.0.0.1:8202",
        chain_id="ait-testchain.local",
    )
    monkeypatch.setattr("aitbc_cli.commands.ai.get_config", lambda: config)
    return config


@pytest.fixture
def mock_http_client(monkeypatch):
    calls = {"post": []}

    class FakeClient:
        def __init__(self, base_url=None, timeout=10, headers=None, **kwargs):
            self.base_url = base_url or "http://127.0.0.1:8203"

        def post(self, path, **kwargs):
            calls["post"].append((self.base_url, path, kwargs))
            return {"job_id": "coord-job-1", "payment_id": "pay-1"}

        def get(self, path, **kwargs):
            return {}

    monkeypatch.setattr("aitbc_cli.commands.ai.AITBCHTTPClient", FakeClient)
    return calls


def _invoke_transcribe(**extra):
    args = [
        "--api-key",
        "test-token",
        "ai",
        "submit",
        "--type",
        "transcribe",
        "--input",
        "https://example.com/audio.mp3",
        "--model",
        "base",
        "--coordinator-url",
        "http://127.0.0.1:8203",
    ]
    for flag, value in extra.items():
        args += [flag, str(value)]
    return CliRunner().invoke(cli, args)


_PAID_ARGS = {"--payment": "1.5", "--provider-address": "0x" + "11" * 20}


@pytest.mark.unit
def test_transcribe_submit_embeds_shop_access_triple(mock_config, mock_http_client):
    with patch(
        "aitbc_cli.commands.market.jobs._register_paid_market_job",
        return_value=("ak_testkey123", "as_testsecret456"),
    ) as mock_register:
        result = _invoke_transcribe(**_PAID_ARGS)

    assert result.exit_code == 0, result.output
    payload = mock_http_client["post"][0][2]["json"]["payload"]
    assert payload["type"] == "transcribe"
    # #2322: the CLI mints the creds itself (they must be in the payload
    # before submit); the market job row is registered afterwards.
    access_key = payload["access_key"]
    access_secret = payload["access_secret"]
    assert access_key and access_secret
    market_job_id = payload["market_job_id"]
    assert market_job_id.startswith("ai_job_")
    # The market job id is a token record, never the coordinator job id —
    # an alias would let pin-confirm resolve the coordinator escrow; the
    # real escrow key travels as escrow_job_id instead.
    assert market_job_id != "coord-job-1"
    assert mock_register.call_args.args[1] == market_job_id
    assert mock_register.call_args.args[5] == "whisper"
    assert mock_register.call_args.kwargs["access_key"] == access_key
    assert mock_register.call_args.kwargs["access_secret"] == access_secret
    assert mock_register.call_args.kwargs["escrow_job_id"] == "coord-job-1"


@pytest.mark.unit
def test_offer_bound_transcribe_submit_embeds_shop_access(mock_config, mock_http_client):
    """An --offer-id submit is priced from the offer quote server-side, so
    it is paid even without --payment and must still mint the token."""
    with patch(
        "aitbc_cli.commands.market.jobs._register_paid_market_job",
        return_value=("ak_testkey123", "as_testsecret456"),
    ) as mock_register:
        result = _invoke_transcribe(**{"--offer-id": "offer-1"})

    assert result.exit_code == 0, result.output
    mock_register.assert_called_once()
    payload = mock_http_client["post"][0][2]["json"]["payload"]
    # #2322: creds are minted locally pre-submit; the mock's return value is
    # not embedded — registration is deferred and carries them by kwargs.
    assert payload["access_key"]
    assert payload["access_secret"]
    assert payload["access_key"] != "ak_testkey123"


@pytest.mark.unit
def test_unpaid_transcribe_submit_mints_no_shop_access(mock_config, mock_http_client):
    """#2321: an unpaid transcribe job is dispatchable — minting a shop token
    for it would hand a free job a valid credential for the gated endpoint."""
    with patch("aitbc_cli.commands.market.jobs._register_paid_market_job") as mock_register:
        result = _invoke_transcribe()

    assert result.exit_code == 0, result.output
    mock_register.assert_not_called()
    payload = mock_http_client["post"][0][2]["json"]["payload"]
    assert payload["type"] == "transcribe"
    assert "access_key" not in payload
    assert "access_secret" not in payload
    assert "market_job_id" not in payload


@pytest.mark.unit
def test_transcribe_submit_without_registration_still_submits(mock_config, mock_http_client):
    """Market-service outage degrades to an unverifiable token (shop 401), not a submit failure.

    #2322: creds are embedded pre-submit regardless — registration is
    # deferred until the coordinator job id is known, so a dead market
    # service can no longer strip them from the payload; the token simply
    # never verifies.
    """
    with patch(
        "aitbc_cli.commands.market.jobs._register_paid_market_job",
        return_value=None,
    ):
        result = _invoke_transcribe(**_PAID_ARGS)

    assert result.exit_code == 0, result.output
    payload = mock_http_client["post"][0][2]["json"]["payload"]
    assert payload["access_key"]
    assert payload["market_job_id"]


@pytest.mark.unit
def test_inference_submit_does_not_mint_shop_access(mock_config, mock_http_client):
    with patch("aitbc_cli.commands.market.jobs._register_paid_market_job") as mock_register:
        result = CliRunner().invoke(
            cli,
            [
                "--api-key",
                "test-token",
                "ai",
                "submit",
                "--type",
                "inference",
                "--prompt",
                "hi",
                "--coordinator-url",
                "http://127.0.0.1:8203",
            ],
        )

    assert result.exit_code == 0, result.output
    mock_register.assert_not_called()
    payload = mock_http_client["post"][0][2]["json"]["payload"]
    assert "access_key" not in payload
