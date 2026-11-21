"""#2405: agent CLI vs the coordinator's signed-read auth.

Player-filed defects:

* ``agent discover agents`` probed ``GET /v1/tasks/status`` *unsigned* before
  computing the ``X-Agent-*`` signed-read headers, so on an auth-enforcing
  coordinator the probe 401'd and the signed discover POST was never reached.
* ``agent inbox``/``agent subscribe`` already sign correctly; the gap was the
  401 error surface not naming ``--wallet``.
* ``agent workflow *`` gates on the shared coordinator API key
  (``X-API-Key``); a 401 now names ``--api-key`` instead of the generic text.
* ``agent status`` read the ``{"status":"success","agent":{...}}`` envelope
  top level — reporting state="success" and registered=False for every agent.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from click.testing import CliRunner

pytest.importorskip("eth_account", reason="signing tests need eth-account")

from eth_account import Account  # noqa: E402

PRIVATE_KEY = "0x" + "42" * 32
ACCOUNT = Account.from_key(PRIVATE_KEY)


@pytest.fixture
def runner():
    return CliRunner()


def _http_error(status_code: int) -> requests.exceptions.HTTPError:
    err = requests.exceptions.HTTPError(f"{status_code} Client Error")
    err.response = MagicMock(status_code=status_code)
    return err


class TestDiscoverProbeSigned:
    """The /v1/tasks/status probe must carry the same X-Agent-* headers as the
    discover POST — it is an auth-gated route too (#2212)."""

    def _invoke(self, runner, signed_headers):
        from aitbc_cli.commands import agent_sdk

        client = MagicMock()
        client.get.return_value = {"status": "ok"}
        client.post.return_value = {"agents": [], "count": 0}
        with (
            patch.object(agent_sdk, "signed_read_headers", return_value=signed_headers),
            patch.object(agent_sdk, "auth_client_kwargs", return_value={}),
            patch.object(agent_sdk, "AITBCHTTPClient", return_value=client),
        ):
            result = runner.invoke(
                agent_sdk.agent,
                ["discover", "agents", "--coordinator-url", "http://coord"],
                obj={"output_format": "json"},
            )
        return result, client

    def test_probe_and_discover_carry_signed_headers(self, runner):
        signed = {"X-Agent-Id": "agent-1", "X-Agent-Signature": "0xsig"}
        result, client = self._invoke(runner, signed)
        assert result.exit_code == 0, result.output

        probe = next(c for c in client.get.call_args_list if c.args[0] == "/v1/tasks/status")
        assert probe.kwargs["headers"] == signed
        discover = next(c for c in client.post.call_args_list if c.args[0] == "/v1/agents/discover")
        assert discover.kwargs["headers"] == signed

    def test_unsigned_probe_still_works(self, runner):
        """No signing configured → the probe goes out unsigned (headers=None)."""
        result, client = self._invoke(runner, None)
        assert result.exit_code == 0, result.output
        probe = next(c for c in client.get.call_args_list if c.args[0] == "/v1/tasks/status")
        assert probe.kwargs["headers"] is None


class TestGetAgentStatusUnwrap:
    """GET /v1/agents/{id} nests the record under ``agent`` — the CLI must not
    read the envelope's ``status: "success"`` as the agent state."""

    def _status(self, payload):
        from aitbc_cli.commands import agent_sdk

        client = MagicMock()
        client.get.return_value = payload
        with (
            patch.object(agent_sdk, "AITBCHTTPClient", return_value=client),
            patch.object(agent_sdk, "get_config", return_value=MagicMock(api_key=None)),
            patch.object(agent_sdk, "auth_client_kwargs", return_value={}),
        ):
            return agent_sdk.get_agent_status("agent-1", coordinator_url="http://coord")

    def test_envelope_shape_unwraps_agent_record(self):
        data = self._status(
            {
                "status": "success",
                "agent": {
                    "agent_id": "agent-1",
                    "agent_type": "worker",
                    "status": "active",
                    "last_heartbeat": "2026-11-20T10:00:00+00:00",
                    "registration_time": "2026-11-01T00:00:00+00:00",
                    "health_score": 0.87,
                },
                "timestamp": "2026-11-20T10:05:00+00:00",
            }
        )
        assert data["registered"] is True
        assert data["status"] == "active"
        assert data["agent_id"] == "agent-1"
        assert data["last_seen"] == "2026-11-20T10:00:00+00:00"
        # health_score is surfaced separately; reputation stays honest at 0.0.
        assert data["reputation_score"] == 0.0
        assert data["health_score"] == 0.87

    def test_flat_record_shape_still_works(self):
        data = self._status({"agent_id": "agent-1", "status": "inactive", "last_heartbeat": "2026-11-19T00:00:00+00:00"})
        assert data["registered"] is True
        assert data["status"] == "inactive"
        assert data["last_seen"] == "2026-11-19T00:00:00+00:00"

    def test_empty_envelope_reports_unregistered(self):
        data = self._status({"status": "success", "timestamp": "2026-11-20T10:05:00+00:00"})
        assert data["registered"] is False
        assert data["status"] == "unknown"


class TestAuthErrorHints:
    """401s on the messages/workflow routes must name the credential to supply."""

    def test_inbox_401_hints_wallet_signing(self, runner):
        from aitbc_cli.commands import agent_sdk

        with (
            patch("requests.get", side_effect=_http_error(401)),
            patch.object(agent_sdk, "load_signing_wallet", return_value=None),
        ):
            result = runner.invoke(
                agent_sdk.agent,
                ["inbox", "--agent-id", "agent-1", "--coordinator-url", "http://coord"],
                obj={"output_format": "json"},
            )
        assert result.exit_code != 0
        assert "--wallet" in result.output
        assert "--api-key" in result.output

    def test_subscribe_401_hints_wallet_signing(self, runner):
        from aitbc_cli.commands import agent_sdk

        with (
            patch("requests.post", side_effect=_http_error(401)),
            patch.object(agent_sdk, "load_signing_wallet", return_value=None),
        ):
            result = runner.invoke(
                agent_sdk.agent,
                ["subscribe", "--agent-id", "agent-1", "--topic", "jobs", "--coordinator-url", "http://coord"],
                obj={"output_format": "json"},
            )
        assert result.exit_code != 0
        assert "--wallet" in result.output

    def test_workflow_401_hints_api_key(self, runner):
        from aitbc_cli.commands import agent_sdk

        with (
            patch("requests.get", side_effect=_http_error(401)),
            patch.object(agent_sdk, "get_config", return_value=MagicMock(api_key=None)),
            patch.object(agent_sdk, "auth_headers", return_value={}),
        ):
            result = runner.invoke(
                agent_sdk.agent,
                ["workflow", "list-workflows", "--coordinator-url", "http://coord"],
                obj={"output_format": "json"},
            )
        assert result.exit_code != 0
        assert "--api-key" in result.output
        assert "wallet" in result.output  # explains signing does not apply
