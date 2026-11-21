"""AI-JOBS-LISTING-1 (#2453): ``aitbc ai jobs`` must render a real table in
``--format table`` (not a raw JSON blob), pass the true ``total``/``has_more``
envelope through in JSON, and answer ``--inflight`` from the aggregate
endpoint without pulling job rows.
"""

from __future__ import annotations

import json
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


_LIST_RESULT: dict[str, Any] = {
    "items": [
        {
            "job_id": "job-1",
            "state": "QUEUED",
            "requested_at": "2026-11-21T10:00:00Z",
            "payment_amount": "0.5",
            "payment_token": "AITBC",
            "payment_status": "pending",
            "assigned_miner_id": None,
            "payload": {"type": "inference", "prompt": "x" * 400},
            "result": None,
        },
        {
            "job_id": "job-2",
            "state": "RUNNING",
            "requested_at": "2026-11-21T09:00:00Z",
            "payment_amount": None,
            "payment_token": None,
            "payment_status": None,
            "assigned_miner_id": "miner-9",
            "payload": {"type": "transcribe"},
            "result": None,
        },
    ],
    "total": 17,
    "has_more": True,
    "limit": 2,
    "offset": 0,
}

_INFLIGHT_RESULT: dict[str, Any] = {"inflight": 3, "cap": 50}


def _mock_client(get_side_effect):
    client = MagicMock()
    client.get.side_effect = get_side_effect
    config = MagicMock()
    config.coordinator_api_url = "http://localhost:8203"
    config.api_key = "test-key"
    return client, config


def _get_router(result):
    def _get(path, params=None):
        return result

    return _get


def _invoke(runner, args, client, config, output_format="json"):
    from aitbc_cli.commands.ai import ai

    with (
        patch("aitbc_cli.commands.ai.AITBCHTTPClient", return_value=client),
        patch("aitbc_cli.commands.ai.get_config", return_value=config),
    ):
        return runner.invoke(ai, args, obj={"output_format": output_format, "api_key": "test-key"})


def test_ai_jobs_table_renders_columns_not_json(runner):
    client, config = _mock_client(_get_router(_LIST_RESULT))
    result = _invoke(runner, ["jobs", "--format", "table"], client, config, output_format="table")
    assert result.exit_code == 0, result.output
    out = result.output
    # Real table: header row + one row per job, no JSON envelope.
    assert "job_id" in out and "state" in out and "requested_at" in out
    assert "job-1" in out and "QUEUED" in out and "job-2" in out and "RUNNING" in out
    assert "0.5 AITBC" in out
    assert '"items"' not in out and '"total"' not in out
    # Summary line carries the true total + has_more.
    assert "total=17" in out and "has_more=True" in out


def test_ai_jobs_json_passes_true_total_envelope(runner):
    client, config = _mock_client(_get_router(_LIST_RESULT))
    result = _invoke(runner, ["jobs", "--format", "json"], client, config)
    assert result.exit_code == 0, result.output
    data = cast(Any, json.loads(result.output))
    assert data["total"] == 17
    assert data["has_more"] is True
    assert len(data["items"]) == 2


def test_ai_jobs_sends_status_filter(runner):
    seen: dict[str, Any] = {}

    def _get(path, params=None):
        seen["path"] = path
        seen["params"] = params
        return _LIST_RESULT

    client, config = _mock_client(_get)
    result = _invoke(runner, ["jobs", "--status", "QUEUED", "--format", "json"], client, config)
    assert result.exit_code == 0, result.output
    assert seen["path"] == "/v1/jobs"
    assert seen["params"]["status"] == "QUEUED"


def test_ai_jobs_inflight_hits_aggregate_endpoint(runner):
    paths: list[str] = []

    def _get(path, params=None):
        paths.append(path)
        return _INFLIGHT_RESULT

    client, config = _mock_client(_get)
    result = _invoke(runner, ["jobs", "--inflight", "--format", "json"], client, config)
    assert result.exit_code == 0, result.output
    assert paths == ["/v1/jobs/inflight"]
    data = cast(Any, json.loads(result.output))
    assert data == {"inflight": 3, "cap": 50}


def test_ai_jobs_inflight_table_shows_field_value(runner):
    client, config = _mock_client(_get_router(_INFLIGHT_RESULT))
    result = _invoke(runner, ["jobs", "--inflight"], client, config, output_format="table")
    assert result.exit_code == 0, result.output
    assert "inflight" in result.output and "cap" in result.output
    assert "3" in result.output and "50" in result.output
