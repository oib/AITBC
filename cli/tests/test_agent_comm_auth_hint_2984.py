"""#2980/#2984 INC-S16 pins: agent-comm registry/inbox reads are
principal-gated — a bare 401 must surface the credential hint instead of
reading like a server fault."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def _http_exc(status: int) -> RuntimeError:
    exc = RuntimeError(f"HTTP {status}")
    exc.response = SimpleNamespace(status_code=status)  # type: ignore[attr-defined]
    return exc


def _invoke(runner, argv, method="post", status=401):
    from aitbc_cli.commands.agent_comm import agent_comm

    client = MagicMock()
    getattr(client, method).side_effect = _http_exc(status)
    obj = {
        "config": MagicMock(coordinator_api_url="http://coord.local", agent_coordinator_url=None, api_key=None),
        "output_format": "table",
    }
    with (
        patch("aitbc_cli.commands.agent_comm._agent_client", return_value=client),
        patch("aitbc_cli.commands.agent_comm.load_signing_wallet", return_value=None),
    ):
        return runner.invoke(agent_comm, argv, obj=obj)


HINT = "principal-gated"


@pytest.mark.parametrize(
    "argv,method",
    [
        (["list"], "post"),
        (["discover", "--chain-id", "ait-mainnet"], "post"),
        (["status", "--agent-id", "a-1"], "get"),
        (["network"], "post"),
        (["receive", "--receiver-id", "a-1"], "get"),
    ],
)
def test_registry_read_401_shows_auth_hint(runner, argv, method):
    result = _invoke(runner, argv, method=method, status=401)
    assert result.exit_code != 0
    assert HINT in result.output
    assert "--signing-agent-id" in result.output


@pytest.mark.parametrize(
    "argv,method",
    [
        (["list"], "post"),
        (["status", "--agent-id", "a-1"], "get"),
        (["receive", "--receiver-id", "a-1"], "get"),
    ],
)
def test_registry_read_500_stays_generic(runner, argv, method):
    result = _invoke(runner, argv, method=method, status=500)
    assert result.exit_code != 0
    assert HINT not in result.output
    assert "HTTP 500" in result.output or "500" in result.output
