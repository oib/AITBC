"""#2434 SEC-MARKET-JOBS-SECRET-LEAK-2: market job read-backs must not print
shop-gate credential material.

``GET /v1/market/jobs`` and ``GET /v1/market/jobs/{id}`` return the stored
job record verbatim, including ``payload.access_key`` and the stored
``payload.access_secret`` digest. ``aitbc market jobs``/``cancel``/
``provider-pin`` rendered those records raw, so the credential pair landed
in logs and scrollback — the same leak class #2355 closed for ``ai``.
The read-back surfaces now run ``redact_secrets`` before rendering;
``access_key`` stays visible as the public half of the pair (the #2355
convention), while ``access_secret`` renders as ``***REDACTED***``.
"""

import json
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

import aitbc_cli.commands.market.host as host_mod
from aitbc_cli.commands.market import market
from aitbc_cli.utils.redact import REDACTED

_PLAINTEXT_SECRET = "as_stored_secret_digest_value"

_JOB: dict[str, Any] = {
    "job_id": "sw_job_redact_1",
    "state": "REFUNDED",
    "service_type": "ipfs",
    "payload": {
        "cid": "bafyExample",
        "access_key": "ak_public_half",
        "access_secret": _PLAINTEXT_SECRET,
    },
    "access_key": "ak_public_half",
    "payment_status": "refunded",
}


class _JobsClient:
    """Answers the list endpoint with a bare array carrying credential fields."""

    def __init__(self, jobs=None):
        self._jobs = jobs if jobs is not None else [_JOB]

    def get_json(self, path, params=None):
        return self._jobs

    def get(self, path, params=None):
        return _JOB

    def post(self, path, json=None):
        return {"job_id": _JOB["job_id"], "state": "CANCELLED"}

    def close(self):
        pass


@pytest.fixture
def runner():
    return CliRunner()


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(host_mod, "_hub_market_client", lambda *a, **kw: client)


def test_market_jobs_json_redacts_access_secret(runner, monkeypatch):
    _patch_client(monkeypatch, _JobsClient())
    result = runner.invoke(market, ["jobs", "--output", "json"], obj={"output_format": "json"})
    assert result.exit_code == 0, result.output
    assert _PLAINTEXT_SECRET not in result.output
    data = cast(Any, json.loads(result.output))
    payload = data[0]["payload"]
    assert payload["access_secret"] == REDACTED
    # Public half of the pair stays readable (#2355 convention).
    assert payload["access_key"] == "ak_public_half"
    assert data[0]["access_key"] == "ak_public_half"


def test_market_jobs_table_output_also_redacts(runner, monkeypatch):
    """The table renderer falls back to JSON for nested records — redaction
    must happen before rendering, not only on the json path."""
    _patch_client(monkeypatch, _JobsClient())
    result = runner.invoke(market, ["jobs"], obj={})
    assert result.exit_code == 0, result.output
    assert _PLAINTEXT_SECRET not in result.output
    assert REDACTED in result.output


def test_market_cancel_refetched_job_redacts(runner, monkeypatch):
    """`market cancel` re-fetches the job and prints it — same leak surface."""
    _patch_client(monkeypatch, _JobsClient())
    monkeypatch.setattr(host_mod, "get_market_wallet", lambda *a, **kw: ("0xabc", None, None))
    monkeypatch.setattr(host_mod, "get_chain_id", lambda: "bc-2")
    monkeypatch.setattr(host_mod, "get_config", lambda: MagicMock())
    monkeypatch.setattr(host_mod, "_post_escrow_rpc", lambda *a, **kw: ({}, []))
    result = runner.invoke(
        market,
        ["cancel", "--job-id", _JOB["job_id"], "--output", "json"],
        obj={"output_format": "json"},
    )
    assert result.exit_code == 0, result.output
    assert _PLAINTEXT_SECRET not in result.output
    # Warning lines precede the rendered record — parse the JSON object.
    lines = result.output.splitlines()
    start = next(i for i, line in enumerate(lines) if line == "{")
    data = cast(Any, json.loads("\n".join(lines[start:])))
    assert data["payload"]["access_secret"] == REDACTED
