"""#2355: ``aitbc ai`` output must not print job-payload credentials.

Paid ``transcribe`` submissions embed a per-job shop-gate credential pair
(``payload.access_key`` / ``payload.access_secret``) in the coordinator job
record. ``ai jobs``/``status``/``results`` render that record verbatim, so
the plaintext secret landed in logs and scrollback. The ai command group's
``output`` wrapper now runs ``redact_secrets`` over the payload first.
"""

from __future__ import annotations

import json
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.utils.redact import REDACTED, redact_secrets, secret_field_name


@pytest.fixture
def runner():
    return CliRunner()


_JOB: dict[str, Any] = {
    "job_id": "job-2355",
    "state": "COMPLETED",
    "payment_token": "AITBC",
    "payload": {
        "type": "transcribe",
        "prompt": "hello",
        "access_key": "ak_public_half",
        "access_secret": "as_plaintext_secret",
        "market_job_id": "ai_job_abc123",
        "public_endpoint": "/ip4/1.2.3.4",
    },
}


def _mock_ai_client(get_return):
    client = MagicMock()
    client.get.return_value = get_return
    config = MagicMock()
    config.coordinator_api_url = "http://localhost:8203"
    config.api_key = "test-key"
    return client, config


def _invoke(runner, args, client, config, output_format="json"):
    from aitbc_cli.commands.ai import ai

    with (
        patch("aitbc_cli.commands.ai.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.commands.ai.get_config", return_value=config),
    ):
        return runner.invoke(ai, args, obj={"output_format": output_format, "api_key": "test-key"})


def test_secret_field_name_matrix():
    denied = [
        "access_secret",
        "secret",
        "password",
        "api_key",
        "private_key",
        "wallet_key",
        "session_token",
        "accessToken",
        "csrf_token",
        "seed",
        "decode_seed",
        "mnemonic",
        "client_secret",
        "pgpassword",
        "auth_key",
        "token",
    ]
    for name in denied:
        assert secret_field_name(name), name

    allowed = [
        "access_key",  # public half of the pair — must stay readable
        "public_key",
        "pubkey",
        "payment_token",  # currency symbol, not a bearer token
        "tokens_used",
        "tokens_processed",
        "idempotency_key",
        "market_job_id",
        "private_key_file",  # path, not the secret
        "job_id",
        "state",
        "signature",
    ]
    for name in allowed:
        assert not secret_field_name(name), name


def test_redact_secrets_recurses_and_keeps_public_fields():
    out = redact_secrets([_JOB])
    payload = out[0]["payload"]
    assert payload["access_secret"] == REDACTED
    assert payload["access_key"] == "ak_public_half"
    assert payload["market_job_id"] == "ai_job_abc123"
    assert out[0]["payment_token"] == "AITBC"
    # input is not mutated
    assert _JOB["payload"]["access_secret"] == "as_plaintext_secret"


def test_ai_jobs_json_redacts_shop_gate_credentials(runner):
    client, config = _mock_ai_client([_JOB])
    result = _invoke(runner, ["jobs", "--format", "json"], client, config)
    assert result.exit_code == 0, result.output
    rendered = result.output
    assert "as_plaintext_secret" not in rendered
    data = cast(Any, json.loads(rendered))
    payload = data[0]["payload"]
    assert payload["access_secret"] == REDACTED
    assert payload["access_key"] == "ak_public_half"
    assert payload["market_job_id"] == "ai_job_abc123"


def test_ai_status_json_redacts_nested_payload(runner):
    client, config = _mock_ai_client(_JOB)
    result = _invoke(runner, ["status", "--job-id", "job-2355", "--format", "json"], client, config)
    assert result.exit_code == 0, result.output
    assert "as_plaintext_secret" not in result.output
    data = cast(Any, json.loads(result.output))
    assert data["payload"]["access_secret"] == REDACTED


def test_ai_results_table_fallback_also_redacts(runner):
    """The table renderer falls back to JSON for nested records — the leak
    path is not json-only, so redaction must happen before rendering."""
    client, config = _mock_ai_client({"job_id": "job-2355", "result": _JOB["payload"]})
    result = _invoke(runner, ["results", "--job-id", "job-2355"], client, config, output_format="table")
    assert result.exit_code == 0, result.output
    assert "as_plaintext_secret" not in result.output
    assert REDACTED in result.output
