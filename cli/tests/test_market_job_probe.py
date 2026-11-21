"""Tests for ``aitbc market job-probe`` and the group ``--api-key`` (#2454).

The probe verb replays the #2326 alias-binding refusal legs through the CLI:
unsigned alias claim -> 403, signature bound to a different escrow key -> 403,
self-bound job -> 200. These tests pin the request body shape, the signature
binding selection, the API-key override, and that the key never echoes.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from aitbc.exceptions import AITBCError
from aitbc_cli.commands.market._group import market


class _FakeResponse:
    def __init__(self, status_code: int, body: dict[str, Any]):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class _ProbeError(AITBCError):
    def __init__(self, status_code: int, body: dict[str, Any]):
        super().__init__(f"HTTP {status_code}")
        self.response = _FakeResponse(status_code, body)


class _FakeClient:
    """Records the POST and replays a canned outcome."""

    def __init__(self, outcome: dict[str, Any] | Exception):
        self.outcome = outcome
        self.posts: list[tuple[str, dict[str, Any]]] = []
        self.api_key: str | None = None

    def post(self, path: str, json: dict[str, Any] | None = None, **_kw):
        self.posts.append((path, json or {}))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _invoke(args: list[str], client: _FakeClient, api_key: str | None = None, sign_fields=None):
    captured: dict[str, Any] = {}

    def _factory(timeout: int = 15, api_key: str | None = None):
        captured["api_key"] = api_key
        client.api_key = api_key
        return client

    sign_patch = (
        patch("aitbc_cli.commands.market._signing.signed_job_request_fields", side_effect=sign_fields)
        if sign_fields is not None
        else patch(
            "aitbc_cli.commands.market._signing.signed_job_request_fields",
            return_value={"signer_address": "0xBuyer", "signature": "0xsig"},
        )
    )
    with (
        patch("aitbc_cli.commands.ipfs._hub_market_client", side_effect=_factory),
        patch(
            "aitbc_cli.commands.market.jobs.get_market_wallet",
            return_value=("0xBuyer0000000000000000000000000000000001", "0xkey", "test"),
        ),
        sign_patch,
    ):
        result = CliRunner().invoke(market, ["--api-key", api_key, *args] if api_key else args)
    return result, client, captured


def _last_body(client: _FakeClient) -> dict[str, Any]:
    return client.posts[-1][1]


def test_unsigned_alias_claim_reports_403():
    client = _FakeClient(_ProbeError(403, {"detail": "alias escrow claims require a buyer wallet signature"}))
    result, client, _ = _invoke(
        ["job-probe", "--escrow-job-id", "coord_probe_1", "--no-signature", "--output", "json"], client
    )
    assert result.exit_code == 0, result.output
    record = json.loads(result.output)
    assert record["http_status"] == 403
    assert record["ok"] is False
    assert record["signed"] is False
    body = _last_body(client)
    assert body["payload"]["escrow_job_id"] == "coord_probe_1"
    assert "signature" not in body
    assert "signer_address" not in body


def test_signed_alias_claim_carries_signature_fields():
    client = _FakeClient({"job_id": "j1", "state": "pending"})
    result, client, _ = _invoke(["job-probe", "--escrow-job-id", "coord_probe_1", "--output", "json"], client)
    assert result.exit_code == 0, result.output
    record = json.loads(result.output)
    assert record["http_status"] == 200
    assert record["signed"] is True
    body = _last_body(client)
    assert body["payload"]["escrow_job_id"] == "coord_probe_1"
    assert body["signature"] == "0xsig"
    assert body["buyer_address"] == "0xBuyer0000000000000000000000000000000001"


def test_mismatch_signature_binds_sign_escrow_job_id():
    client = _FakeClient(_ProbeError(403, {"detail": "signature/binding mismatch"}))
    bindings: list[dict[str, Any]] = []

    def _sign(ctx, route, *, wallet=None, binding=None):
        bindings.append(binding or {})
        return {"signature": "0xsig"}

    result, client, _ = _invoke(
        [
            "job-probe",
            "--escrow-job-id",
            "coord_probe_2",
            "--sign-escrow-job-id",
            "coord_probe_1",
            "--output",
            "json",
        ],
        client,
        sign_fields=_sign,
    )
    assert result.exit_code == 0, result.output
    assert bindings == [{"escrow_job_id": "coord_probe_1", "buyer_address": "0xBuyer0000000000000000000000000000000001"}]
    assert _last_body(client)["payload"]["escrow_job_id"] == "coord_probe_2"


def test_self_bound_job_needs_no_signature():
    client = _FakeClient({"job_id": "j2", "state": "pending"})
    result, client, _ = _invoke(["job-probe", "--output", "json"], client)
    assert result.exit_code == 0, result.output
    record = json.loads(result.output)
    assert record["http_status"] == 200
    body = _last_body(client)
    assert "escrow_job_id" not in body["payload"]
    assert "signature" not in body


def test_group_api_key_override_reaches_client_and_never_echoes():
    client = _FakeClient({"job_id": "j3"})
    result, client, captured = _invoke(["job-probe", "--output", "json"], client, api_key="user-tier-secret")
    assert result.exit_code == 0, result.output
    assert captured["api_key"] == "user-tier-secret"
    assert client.api_key == "user-tier-secret"
    assert "user-tier-secret" not in result.output


def test_explicit_buyer_address_used_for_claim():
    client = _FakeClient(_ProbeError(403, {"detail": "nope"}))
    result, client, _ = _invoke(
        ["job-probe", "--no-signature", "--buyer-address", "0xCustomBuyer", "--escrow-job-id", "e1", "--output", "json"],
        client,
    )
    assert result.exit_code == 0, result.output
    assert _last_body(client)["buyer_address"] == "0xCustomBuyer"
