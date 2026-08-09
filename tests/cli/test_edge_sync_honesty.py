"""V23-17: the CLI must not restate a claim the service stopped making.

``aitbc edge database sync-db`` took ``result["success"]`` as its cue to print
"Database X synced". Once the service began labelling simulated responses, that
label was discarded one layer up — the client repeating the very claim the fix
removed from the server. These tests pin the client side of the finding.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from aitbc_cli.commands.edge import edge


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError("raise_for_status must not be reached for a handled status")


class FakeClient:
    def __init__(self, response: FakeResponse):
        self._response = response
        self.posted: list[str] = []

    def post(self, url: str, **kwargs) -> FakeResponse:
        self.posted.append(url)
        return self._response


@pytest.fixture
def runner():
    return CliRunner()


def _invoke(runner, response: FakeResponse):
    client = FakeClient(response)
    with patch("aitbc_cli.commands.edge.get_edge_client", return_value=client):
        result = runner.invoke(edge, ["database", "sync-db", "db_123"], obj={"output": "json"})
    return result, client


def test_501_reports_the_server_explanation(runner):
    """Not a bare status line — the detail says what is and is not implemented."""
    detail = "Edge database sync is not implemented. This endpoint previously reported success..."
    result, client = _invoke(runner, FakeResponse(501, {"detail": detail}))

    assert client.posted == ["/v1/database/db_123/sync"]
    assert "not implemented" in result.output
    assert "synced" not in result.output


def test_simulated_response_is_not_reported_as_synced(runner):
    """The label survives the trip through the client."""
    result, _ = _invoke(
        runner,
        FakeResponse(
            200,
            {
                "success": True,
                "simulated": True,
                "message": "Simulated sync for db_123: no data was transferred",
                "records_synced": 4242,
            },
        ),
    )

    assert "no data was transferred" in result.output
    assert "Database db_123 synced" not in result.output


def test_real_success_still_reports_synced(runner):
    """The honest path is unchanged, so the change costs nothing once sync exists."""
    result, _ = _invoke(runner, FakeResponse(200, {"success": True, "records_synced": 100}))

    assert "Database db_123 synced" in result.output


def test_failure_payload_is_reported_as_an_error(runner):
    result, _ = _invoke(runner, FakeResponse(200, {"success": False, "message": "Database db_123 not found"}))

    assert "not found" in result.output
    assert "Database db_123 synced" not in result.output


def test_payload_is_still_printed_in_simulated_mode(runner):
    """The warning replaces the success line, it does not replace the response body.

    Asserted on the flattened output because the payload is rendered through rich,
    which hard-wraps to the terminal width and would otherwise make this brittle.
    """
    result, _ = _invoke(
        runner,
        FakeResponse(200, {"success": True, "simulated": True, "message": "sim", "records_synced": 4242}),
    )

    flattened = "".join(result.output.split())
    assert '"simulated":true' in flattened
    assert '"records_synced":4242' in flattened
