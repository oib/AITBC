"""Tests for the compliance hook in `aitbc ai submit`."""

import json
import re
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.ai import ai


def _parse_json_output(output: str) -> dict:
    match = re.search(r"\{.*\}", output, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in output: {output!r}")
    return json.loads(match.group(0))


@pytest.fixture
def runner():
    return CliRunner()


def test_submit_blocks_disallowed_classification(runner):
    result = runner.invoke(
        ai,
        [
            "submit",
            "--type",
            "inference",
            "--prompt",
            "test",
            "--compliance-framework",
            "hipaa",
            "--classification",
            "public",
        ],
    )
    assert result.exit_code != 0
    assert "public" in result.output
    assert "hipaa" in result.output


def test_submit_passes_compliance_and_adds_constraint(runner):
    with patch("aitbc_cli.commands.ai.AITBCHTTPClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.post.return_value = {"job_id": "job-123"}
        mock_client_class.return_value = mock_client
        result = runner.invoke(
            ai,
            [
                "submit",
                "--type",
                "inference",
                "--prompt",
                "test",
                "--compliance-framework",
                "hipaa",
                "--classification",
                "phi",
                "--coordinator-url",
                "http://localhost:8203",
            ],
        )
    assert result.exit_code == 0, result.output
    data = _parse_json_output(result.output)
    assert data["job_id"] == "job-123"
    call_args = mock_client.post.call_args
    assert call_args.kwargs["json"]["constraints"]["data_classification"] == "phi"
